import { expect, test } from 'claude-code/testing'
import type { Plugin } from 'claude-code/testing'

/** Stands in for skills-mcp, the owner of the index: a call of the `seed` tool writes it. */
const owner: Plugin = {
  name: 'skills-mcp',
  register: on => {
    on('tool.call', async ($, e, next) => {
      if (e.tool !== 'seed') return next(e)
      await $.state.set({ plugin: 'skills-mcp', key: 'skills' }, [
        {
          name: 'commit-message',
          label: 'commit-message',
          description: 'Write a commit message',
          uri: 'skill://commit-message/SKILL.md',
          server: 'skills',
        },
      ])
      return { result: 'seeded' }
    })
  },
}

const PANE = {
  component: 'Pane',
  requestId: 'mcp-skills',
  props: { title: 'MCP skills', isFocused: true, bodyColumns: 80, placement: 'dock' },
} as const

test('the pane lists the skills, and a pick previews its SKILL.md', { plugins: [owner] }, async ($, on) => {
  on('tool.call', { tool: 'ReadMcpResourceTool' }, ($, e) => ({
    result: { contents: [{ uri: e.uri, text: '# Commit message\nWrite it well.' }] },
  }))
  await $.tool.call({ tool: 'seed' })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'skills-mcp-browser', surface, ...PANE })
    expect((await ui.find({ type: 'Text', text: /1 MCP skills/ }))).toBeDefined()

    await ui.press({ key: 'skill-commit-message' })
    expect(await ui.find({ type: 'Text', text: /skills · skill:\/\/commit-message\/SKILL\.md/ })).toBeDefined()

    await ui.press({ key: 'preview' })
    const markdown = await ui.find({ type: 'Markdown' })
    expect(markdown?.props.text).toBe('# Commit message\nWrite it well.')
    await ui.unmount()
  }
})

test('with no index yet the pane says so', async $ => {
  const ui = await $.ui.mount({ plugin: 'skills-mcp-browser', surface: 'terminal', ...PANE })
  expect(await ui.find({ type: 'Text', text: /No connected MCP server serves skill:\/\/ resources/ })).toBeDefined()
})
