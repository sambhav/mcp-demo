import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'
import type { Plugin } from 'claude-code/testing'

/**
 * Stands in for skills-mcp, the owner of the index: a call of the `seed` tool writes it.
 * An inline plugin is loaded from its source, so it closes over nothing of this file.
 */
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

/** A session whose `skills` server serves SKILL.md as a resource, and whose own commands are `taken`. */
function session(on: On, registered: string[], taken: string[] = []) {
  on('command.list', () => ({ value: taken.map(name => ({ name, description: '', source: 'user' as const })) }))
  on('command.register', ($, e) => {
    registered.push(e.name)
    return { value: { command: e.name } }
  })
  on('tool.call', { tool: 'ReadMcpResourceTool' }, ($, e) => ({
    result: { contents: [{ uri: e.uri, text: `BODY of ${e.uri} on ${e.server}` }] },
  }))
}

test('/<skill> args starts a turn with SKILL.md beside the request', { plugins: [owner] }, async ($, on) => {
  const registered: string[] = []
  session(on, registered)
  on('prompt.submit', ($, e) => ({ text: e.text, context: e.context }))

  await $.tool.call({ tool: 'seed' })
  expect(registered).toEqual(['commit-message'])

  const entered = await $.prompt.submit({ text: '/commit-message fix the parser' })
  expect(entered.text).toBe('Use the commit-message skill: fix the parser')
  expect(entered.context?.[0]).toContain('BODY of skill://commit-message/SKILL.md on skills')
  expect(entered.context?.[0]).toContain('relative to skill://commit-message/')

  const other = await $.prompt.submit({ text: '/compact' })
  expect(other.text).toBe('/compact')
})

test('the command itself loads the skill for the next turn', { plugins: [owner] }, async ($, on) => {
  session(on, [])
  await $.tool.call({ tool: 'seed' })
  const ran = await $.command.run({ command: 'commit-message', args: '' })
  expect(ran.text).toBe('Loaded the commit-message skill; it applies to your next message.')
  expect(ran.context?.[0]).toContain('BODY of skill://commit-message/SKILL.md')
})

test('a name already taken is left alone', { plugins: [owner] }, async ($, on) => {
  const registered: string[] = []
  session(on, registered, ['commit-message'])
  await $.tool.call({ tool: 'seed' })
  expect(registered).toEqual([])
})
