import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const RESOURCES = [
  { uri: 'skill://commit-message/SKILL.md', name: 'commit-message', description: 'Write a commit message', server: 'skills' },
  { uri: 'skill://commit-message/references/style.md', name: 'style.md', server: 'skills' },
  { uri: 'skill://acme/billing/refunds/SKILL.md', name: 'refunds', description: 'Process refunds', server: 'skills' },
  { uri: 'skill://refunds/SKILL.md', name: 'refunds', description: 'Other refunds', server: 'other' },
  { uri: 'file:///README.md', name: 'README.md', server: 'other' },
]

/** Stands in for a session whose MCP servers list RESOURCES, beneath the plugin. */
function session(on: On, commands: string[] = []) {
  on('ui.status', () => ({ value: undefined }))
  on('store.get', () => ({ value: undefined }))
  on('store.set', () => ({ value: undefined }))
  on('command.list', () => ({ value: commands.map(name => ({ name, description: '', source: 'mcp' as const })) }))
  on('tool.call', { tool: 'ListMcpResourcesTool' }, () => ({ result: RESOURCES }))
}

test('skill:// SKILL.md resources become the index; other resources do not', async ($, on) => {
  session(on)
  const ran = await $.command.run({ command: 'skills-mcp', args: '' })
  expect(ran.text).toContain('3 MCP skills:')
  expect(ran.text).toContain('commit-message  Write a commit message')
  expect(ran.text).not.toContain('style.md')
  expect(ran.text).not.toContain('README')
})

test('a name two servers share is told apart by server', async ($, on) => {
  session(on)
  const ran = await $.command.run({ command: 'skills-mcp', args: '' })
  expect(ran.text).toContain('skills:refunds  Process refunds')
  expect(ran.text).toContain('other:refunds  Other refunds')
})

test('skills Claude Code already loads natively are left to it', async ($, on) => {
  session(on, ['skills:commit-message'])
  const ran = await $.command.run({ command: 'skills-mcp', args: '' })
  expect(ran.text).toContain('2 MCP skills:')
  expect(ran.text).not.toContain('commit-message')
})

test('the index reaches the system prompt with how to read a skill', async ($, on) => {
  session(on)
  on('prompt.compose', () => ({ sections: [{ id: 'intro', text: 'hi', scope: 'shared' as const }] }))
  await $.command.run({ command: 'skills-mcp', args: '' })
  const composed = await $.prompt.compose({ model: 'm', promptModel: 'm', surfaces: [], tools: [], outputStyle: null, traits: [] })
  const section = composed.sections.find(s => s.id === 'skills-mcp:index')
  expect(section?.scope).toBe('session')
  expect(section?.text).toContain('ReadMcpResourceTool')
  expect(section?.text).toContain('- commit-message: Write a commit message (server: skills, uri: skill://commit-message/SKILL.md)')
})

test('a failed listing is reported, not thrown', async ($, on) => {
  on('ui.status', () => ({ value: undefined }))
  on('store.get', () => ({ value: undefined }))
  on('command.list', () => ({ value: [] }))
  on('tool.call', { tool: 'ListMcpResourcesTool' }, () => ({ deny: 'no servers' }))
  const ran = await $.command.run({ command: 'skills-mcp', args: '' })
  expect(ran.text).toBe('Could not read the MCP skill index: no servers')
})
