import { atom, read, update } from 'claude-code'
import type { EngineInterface, PluginState, Register } from 'claude-code'

import type { SkillPreview } from '../types'

type RemoteSkill = PluginState['skills-mcp']['skills'][number]

const PANE = 'mcp-skills'
const skills = atom({ plugin: 'skills-mcp', key: 'skills' } as const, [] as RemoteSkill[])
const status = atom({ plugin: 'skills-mcp', key: 'status' } as const, {})
const selected = atom({ plugin: 'skills-mcp-browser', key: 'selected' } as const, null as string | null)
const preview = atom({ plugin: 'skills-mcp-browser', key: 'preview' } as const, null as SkillPreview | null)

async function loadPreview($: EngineInterface, skill: RemoteSkill) {
  const ran = await $.tool.call({ tool: 'ReadMcpResourceTool', server: skill.server, uri: skill.uri })
  const text =
    ran.deny !== undefined ? `Could not read: ${ran.deny}`
    : ran.isError ? `Could not read: ${String(ran.result)}`
    : ran.result.error ?? ran.result.contents.map(c => c.text ?? '').join('\n')
  await update($, preview, () => ({ name: skill.label, text }))
}

async function useSkill($: EngineInterface, skill: RemoteSkill) {
  // With skills-mcp-commands enabled the skill is a slash command; else ask in words.
  const command = skill.label.replace(/[^A-Za-z0-9_-]/g, '-')
  const isCommand = (await $.command.list()).some(c => c.name === command && c.plugin === 'skills-mcp-commands')
  await $.prompt.fill({ text: isCommand ? `/${command} ` : `Use the ${skill.label} skill to ` })
  await $.ui.close({ id: PANE })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'mcp-skills',
      description: 'Browse the skills an MCP skills server serves',
    })
    return next(e)
  })

  on('command.run', { command: 'mcp-skills' }, async $ => {
    await $.ui.open({ id: PANE, title: 'MCP skills', focus: true, closeOnEscape: true })
    return { text: 'MCP skills pane opened.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Markdown, Text } = $.ui.resolve(e)
    const list = await read($, skills)
    const { error } = await read($, status)
    const chosen = await read($, selected)
    const shown = await read($, preview)
    const skill = list.find(s => s.label === chosen)
    const width = e.props.bodyColumns ?? 60

    if (list.length === 0) {
      return <Text dimColor>{error ? `Could not read the MCP skill index: ${error}` : 'No connected MCP server serves skill:// resources.'}</Text>
    }

    return (
      <Box flexDirection="column">
        <Text dimColor>
          {list.length} MCP skills
        </Text>
        {list.map(s => (
          <Button
            key={`skill-${s.label}`}
            plain
            onPress={() => update($, selected, () => s.label)}
          >
            {s.label === chosen ? '▸ ' : '  '}
            {s.label} <Text dimColor>{s.description.slice(0, Math.max(10, width - s.label.length - 6))}</Text>
          </Button>
        ))}
        {skill && (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>{skill.label}</Text>
            <Text>{skill.description}</Text>
            <Text dimColor>
              {skill.server} · {skill.uri}
            </Text>
            <Box>
              <Button key="use" variant="primary" label="Use" hotkey="u" onPress={() => useSkill($, skill)} />
              <Button key="preview" label="Preview" hotkey="p" onPress={() => loadPreview($, skill)} />
            </Box>
            {shown?.name === skill.label && <Markdown text={shown.text} />}
          </Box>
        )}
      </Box>
    )
  })
}
