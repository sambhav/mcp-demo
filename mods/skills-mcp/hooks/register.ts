import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { RemoteSkill, SkillsMcpStatus } from '../types'

const skills = atom({ plugin: 'skills-mcp', key: 'skills' } as const, [] as RemoteSkill[])
const status = atom({ plugin: 'skills-mcp', key: 'status' } as const, {} as SkillsMcpStatus)

const SECTION_ID = 'skills-mcp:index'
const STORE_KEY = 'skills-mcp:index'
/** `skill://<skill-path>/SKILL.md`, the skill's name the path's last segment (SEP-2640). */
const SKILL_MD = /^skill:\/\/(?:.+\/)?([a-z0-9][a-z0-9-]*)\/SKILL\.md$/

type ListedResource = { uri: string; name: string; description?: string; server: string }

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/** The skills among the listed resources, labelled `server:name` where two servers share a name. */
function toSkills(resources: readonly ListedResource[]): RemoteSkill[] {
  const found = resources.flatMap(r => {
    const name = SKILL_MD.exec(r.uri)?.[1]
    return name ? [{ name, label: name, description: r.description ?? '', uri: r.uri, server: r.server }] : []
  })
  const servers = new Map<string, Set<string>>()
  for (const s of found) servers.set(s.name, (servers.get(s.name) ?? new Set()).add(s.server))
  return found.map(s => ((servers.get(s.name)?.size ?? 0) > 1 ? { ...s, label: `${s.server}:${s.name}` } : s))
}

/** Skills Claude Code already loads natively (as `<server>:<name>`) are left to it. */
async function withoutNative($: EngineInterface, list: RemoteSkill[]): Promise<RemoteSkill[]> {
  const commands = new Set((await $.command.list()).map(c => c.name))
  return list.filter(s => !commands.has(`${s.server}:${s.name}`))
}

async function refresh($: EngineInterface, server: string): Promise<RemoteSkill[]> {
  try {
    const ran = await $.tool.call({ tool: 'ListMcpResourcesTool', ...(server ? { server } : {}) })
    if (ran.deny !== undefined) throw new Error(ran.deny)
    if (ran.isError) throw new Error(String(ran.result ?? 'ListMcpResourcesTool failed'))
    const fresh = await withoutNative($, toSkills(ran.result as ListedResource[]))
    // The index rides in the system prompt: write it only when it changed, so the prompt cache holds.
    if (JSON.stringify(await read($, skills)) !== JSON.stringify(fresh)) {
      await update($, skills, () => fresh)
      await $.store.set(STORE_KEY, fresh)
    }
    await update($, status, () => ({ refreshedAt: Date.now() }))
    $.ui.status(fresh.length ? `${fresh.length} MCP skills` : undefined)
    return fresh
  } catch (err) {
    await update($, status, s => ({ ...s, error: errorText(err) }))
    return read($, skills)
  }
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
  const refreshMs = Number(options.refreshSeconds ?? 300) * 1000

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
