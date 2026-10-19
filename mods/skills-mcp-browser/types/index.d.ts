export type SkillPreview = { name: string; text: string }

declare module 'claude-code' {
  interface PluginState {
    'skills-mcp-browser': {
      selected: string | null
      preview: SkillPreview | null
    }
  }
}
