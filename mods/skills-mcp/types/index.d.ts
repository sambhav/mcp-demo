/** One skill an MCP server serves, found as a `skill://<path>/SKILL.md` resource. */
export type RemoteSkill = {
  /** The skill's name: the last segment of its path. */
  name: string
  /** What the model and the person call it: `name`, or `server:name` when two servers serve one name. */
  label: string
  description: string
  /** The SKILL.md resource's URI. */
  uri: string
  /** The MCP server serving it, as /mcp lists it. */
  server: string
}

export type SkillsMcpStatus = {
  /** When the index was last read from the servers, as ms since the epoch. */
  refreshedAt?: number
  error?: string
}

declare module 'claude-code' {
  interface PluginState {
    'skills-mcp': {
      skills: RemoteSkill[]
      status: SkillsMcpStatus
    }
  }
}
