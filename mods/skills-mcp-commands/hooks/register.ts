import { atom, read } from 'claude-code'
import type { EngineInterface, PluginState, Register } from 'claude-code'

// Declared by the skills-mcp contract, which the engine lays in as a dependency.
type RemoteSkill = PluginState['skills-mcp']['skills'][number]

const skills = atom({ plugin: 'skills-mcp', key: 'skills' } as const, [] as RemoteSkill[])

const SLASH = /^\/(\S+)\s*([\s\S]*)$/

/** Command name -> the skill's SKILL.md, for the commands this module registered. */
const served = new Map<string, { label: string; server: string; uri: string }>()

/** `/<label>`, the `server:` of a disambiguated label spelled `server-` (commands take no colon). */
function commandFor(skill: RemoteSkill, prefix: string): string {
  return `${prefix}${skill.label.replace(/[^A-Za-z0-9_-]/g, '-')}`.slice(0, 64)
}

async function sync($: EngineInterface, list: readonly RemoteSkill[], prefix: string) {
  const taken = new Set(
    (await $.command.list()).filter(c => c.plugin !== $.plugin.name).map(c => c.name),
  )
  for (const skill of list) {
    const command = commandFor(skill, prefix)
    if (taken.has(command)) continue
    await $.command.register({
      name: command,
      description: `${skill.description} (MCP skill, ${skill.server})`,
      argumentHint: '[args]',
    })
    served.set(command, { label: skill.label, server: skill.server, uri: skill.uri })
  }
}

/** The skill's SKILL.md, read as an MCP resource and framed for the model; or why it could not be. */
async function readSkill($: EngineInterface, command: string) {
  const skill = served.get(command)
  if (skill === undefined) return { error: `/${command} is not an MCP skill.` }
  if (!(await read($, skills)).some(s => s.uri === skill.uri && s.server === skill.server)) {
    return { error: `${skill.server} no longer serves ${skill.label}.` }
  }
  const ran = await $.tool.call({ tool: 'ReadMcpResourceTool', server: skill.server, uri: skill.uri })
  if (ran.deny !== undefined) return { error: `Could not read ${skill.uri}: ${ran.deny}` }
  if (ran.isError) return { error: `Could not read ${skill.uri}: ${String(ran.result)}` }
  const text = ran.result.contents.map(c => c.text ?? '').join('\n')
  if (ran.result.error || !text) return { error: `Could not read ${skill.uri}: ${ran.result.error ?? 'empty'}` }
  const folder = skill.uri.replace(/\/SKILL\.md$/, '')
  return {
    label: skill.label,
    text: [
      `<skill name="${skill.label}" server="${skill.server}" uri="${skill.uri}">`,
      text,
      '</skill>',
      `Paths this skill mentions are relative to ${folder}/: read them with ReadMcpResourceTool (server "${skill.server}").`,
    ].join('\n'),
  }
}

export const register: Register = (on, options) => {
  const prefix = String(options.prefix ?? '')

  on('session.start', async ($, e, next) => {
    const ran = await next(e)
    await sync($, await read($, skills), prefix)
    return ran
  })

  // skills-mcp owns the index; follow its writes to register what is new.
  on('state.set', { plugin: 'skills-mcp', key: 'skills' }, async ($, e, next) => {
    const ran = await next(e)
    await sync($, e.value, prefix)
    return ran
  }).catch(($, e, next) => next(e))

  // `/<skill> args` typed: the turn starts with the request, the skill's text beside it
  // for the model, as a local skill's slash command does.
  on('prompt.submit', async ($, e, next) => {
    const [, command = '', args = ''] = SLASH.exec(e.text.trim()) ?? []
    if (!served.has(command)) return next(e)
    const skill = await readSkill($, command)
    if (skill.error !== undefined) return next(e) // command.run below reports it
    const request = args.trim()
    const text = request ? `Use the ${skill.label} skill: ${request}` : `Use the ${skill.label} skill.`
    return next({ ...e, text, context: [...(e.context ?? []), skill.text] })
  }).catch(($, e, next) => next(e))

  // Reached only when the prompt above was not rewritten: say why, or load it for the next turn.
  on('command.run', async ($, e, next) => {
    if (!served.has(e.command)) return next(e)
    const skill = await readSkill($, e.command)
    if (skill.error !== undefined) return { text: skill.error }
    return { text: `Loaded the ${skill.label} skill; it applies to your next message.`, context: [skill.text] }
  }).catch(($, e, next) => (next.called ? next(e) : { text: `/${e.command}: the MCP skill could not be read.` }))
}
