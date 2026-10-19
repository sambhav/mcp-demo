import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { RemoteSkill, SkillsMcpStatus } from '../types'

const skills = atom({ plugin: 'skills-mcp', key: 'skills' } as const, [] as RemoteSkill[])
const status = atom({ plugin: 'skills-mcp', key: 'status' } as const, {} as SkillsMcpStatus)

const SECTION_ID = 'skills-mcp:index'
const STORE_KEY = 'skills-mcp:index'
/** `skill://<skill-path>/SKILL.md`, the skill's name the path's last segment (SEP-2640). */
const SKILL_MD = /^skill:\/\/(?:.+\/)?([a-z0-9][a-z0-9-]*)\/SKILL\.md$/
/**
 * The pre-v1 SEP-2640 index a server may still publish. Claude Code caches resources/list, but
 * reads go to the server, so polling it sees skills added since connect.
 */
const INDEX_URI = 'skill://index.json'

type ListedResource = { uri: string; name: string; description?: string; server: string }
/** Either pre-v1 shape: `url` + `frontmatter` (as servers shipped it), or top-level `name` / `description`. */
type IndexEntry = { url: string; name?: string; description?: string; frontmatter?: { name?: string; description?: string } }

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/** Labels skills `server:name` where two servers share a name. */
function labelled(found: readonly Omit<RemoteSkill, 'label'>[]): RemoteSkill[] {
  const servers = new Map<string, Set<string>>()
  for (const s of found) servers.set(s.name, (servers.get(s.name) ?? new Set()).add(s.server))
  return found.map(s => ({ ...s, label: (servers.get(s.name)?.size ?? 0) > 1 ? `${s.server}:${s.name}` : s.name }))
}

/** The skills among a server's listed resources. */
function fromListing(resources: readonly ListedResource[]) {
  return resources.flatMap(r => {
    const name = SKILL_MD.exec(r.uri)?.[1]
    return name ? [{ name, description: r.description ?? '', uri: r.uri, server: r.server }] : []
  })
}

/** Skills Claude Code already loads natively (as `<server>:<name>`) are left to it. */
async function withoutNative($: EngineInterface, list: RemoteSkill[]): Promise<RemoteSkill[]> {
  const commands = new Set((await $.command.list()).map(c => c.name))
  return list.filter(s => !commands.has(`${s.server}:${s.name}`))
}

/** A server's live index, or undefined when it publishes none or the read fails. */
async function readIndex($: EngineInterface, server: string) {
  const ran = await $.tool.call({ tool: 'ReadMcpResourceTool', server, uri: INDEX_URI })
  if (ran.deny !== undefined || ran.isError || ran.result.error) return undefined
  const index = JSON.parse(ran.result.contents.map(c => c.text ?? '').join('')) as { skills?: IndexEntry[] }
  return (index.skills ?? []).flatMap(e => {
    const name = e.frontmatter?.name ?? e.name ?? SKILL_MD.exec(e.url)?.[1]
    const description = e.frontmatter?.description ?? e.description ?? ''
    return name && SKILL_MD.test(e.url) ? [{ name, description, uri: e.url, server }] : []
  })
}

/** Whether this session has read the servers once: the first read replaces the cached index unannounced. */
let hasRead = false

async function refresh($: EngineInterface, server: string): Promise<RemoteSkill[]> {
  try {
    const ran = await $.tool.call({ tool: 'ListMcpResourcesTool', ...(server ? { server } : {}) })
    if (ran.deny !== undefined) throw new Error(ran.deny)
    if (ran.isError) throw new Error(String(ran.result ?? 'ListMcpResourcesTool failed'))
    const listed = ran.result as ListedResource[]
    const found = []
    for (const name of new Set(listed.map(r => r.server))) {
      const own = listed.filter(r => r.server === name)
      // The listing is as of connect; a server's index is read live, so new skills show at once.
      const live = own.some(r => r.uri === INDEX_URI) ? await readIndex($, name) : undefined
      found.push(...(live ?? fromListing(own)))
    }
    const fresh = await withoutNative($, labelled(found))
    const previous = await read($, skills)
    // The index rides in the system prompt: write it only when it changed, so the prompt cache holds.
    if (JSON.stringify(previous) !== JSON.stringify(fresh)) {
      await update($, skills, () => fresh)
      await $.store.set(STORE_KEY, fresh)
      if (hasRead) await announce($, previous, fresh)
    }
    hasRead = true
    await update($, status, () => ({ refreshedAt: Date.now() }))
    $.ui.status(fresh.length ? `${fresh.length} MCP skills` : undefined)
    return fresh
  } catch (err) {
    await update($, status, s => ({ ...s, error: errorText(err) }))
    return read($, skills)
  }
}

/**
 * Tells the person (a toast) and the model (a note in the conversation, read from its next
 * request, mid-turn included) what came and went. The note matters where a managed plugin keeps
 * user mods out of the system prompt, and it shows the change the moment it lands.
 */
async function announce($: EngineInterface, before: readonly RemoteSkill[], after: readonly RemoteSkill[]) {
  const had = new Map(before.map(s => [s.label, s]))
  const has = new Map(after.map(s => [s.label, s]))
  const added = after.filter(s => !had.has(s.label))
  const removed = before.filter(s => !has.has(s.label))
  const edited = after.filter(s => had.has(s.label) && had.get(s.label)?.description !== s.description)
  if (added.length + removed.length + edited.length === 0) return

  $.ui.toast(`MCP skills: ${[...added.map(s => `+${s.label}`), ...removed.map(s => `-${s.label}`), ...edited.map(s => `~${s.label}`)].join(' ')}`)
  const line = (s: RemoteSkill) => `- ${s.label}: ${s.description} (server: ${s.server}, uri: ${s.uri})`
  const text = [
    'The MCP skills available changed just now.',
    ...(added.length ? ['Added:', ...added.map(line)] : []),
    ...(edited.length ? ['Changed:', ...edited.map(line)] : []),
    ...(removed.length ? [`Removed (no longer available): ${removed.map(s => s.label).join(', ')}`] : []),
    'To use one, read its SKILL.md with ReadMcpResourceTool (server and uri above) before the task, then follow it.',
  ].join('\n')
  await $.session.append({ message: { type: 'user', content: [{ type: 'text', text }] } })
}

/** Seeds the index from the last session's, so the first turn has it before the servers answer. */
async function seed($: EngineInterface) {
  const cached = await $.store.get(STORE_KEY)
  if (Array.isArray(cached) && (await read($, skills)).length === 0) {
    await update($, skills, () => cached as RemoteSkill[])
  }
}

function indexSection(list: readonly RemoteSkill[]): string {
  return [
    '# Skills served over MCP',
    "MCP servers serve these Agent Skills as resources. When a task matches a skill's",
    'description, read its SKILL.md with ReadMcpResourceTool (the server and uri below)',
    'before starting, then follow it. Paths a skill mentions are relative to its folder:',
    'for skill://<path>/SKILL.md, `references/x.md` is skill://<path>/references/x.md, read',
    'the same way; ReadMcpResourceDirTool lists a folder. This index is kept current for',
    'you: do not list resources to look for skills. The person can also run one as /<name>.',
    '',
    ...list.map(s => `- ${s.label}: ${s.description} (server: ${s.server}, uri: ${s.uri})`),
  ].join('\n')
}

export const register: Register = (on, options) => {
  const server = String(options.server ?? '')
  const refreshMs = Number(options.refreshSeconds ?? 2) * 1000

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'skills-mcp',
      description: 'Re-read the skills MCP servers serve',
    })
    await seed($)
    void refresh($, server)
    if (refreshMs > 0) $.clock.every(refreshMs, () => void refresh($, server))
    return next(e)
  })

  on('command.run', { command: 'skills-mcp' }, async $ => {
    const list = await refresh($, server)
    const { error } = await read($, status)
    if (error) return { text: `Could not read the MCP skill index: ${error}` }
    if (list.length === 0) return { text: 'No connected MCP server serves skill:// resources.' }
    return { text: [`${list.length} MCP skills:`, ...list.map(s => `  ${s.label}  ${s.description}`)].join('\n') }
  })

  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    const list = await read($, skills)
    if (list.length === 0 || e.traits.includes('bare')) return composed
    return { sections: [...composed.sections, { id: SECTION_ID, text: indexSection(list), scope: 'session' as const }] }
  })
}
