/**
 * Minimal ambient declarations for the host extension API.
 *
 * Only the surface Greenlight uses is declared, so `tsc --noEmit` works without network
 * access or the (unpublished) harness package. This is not a substitute for the real
 * types — it exists so a type error in this plugin cannot ship, which is exactly how a
 * `GATED.has(...)`-on-a-Record bug once made every tool call fail closed.
 */
declare module "@oh-my-pi/pi-coding-agent" {
  export interface ExtensionUIContext {
    notify(message: string, level?: string): void;
    confirm(title: string, body?: string): Promise<boolean>;
  }

  export interface ExtensionContext {
    hasUI: boolean;
    cwd: string;
    ui: ExtensionUIContext;
  }

  export interface ToolCallEvent {
    toolName: string;
    input: unknown;
    toolCallId?: string;
  }

  export interface ToolResultEvent {
    toolName: string;
    toolCallId?: string;
    input: unknown;
    isError?: boolean;
  }

  export interface AgentStartEvent {
    prompt?: string;
  }

  export interface ExtensionAPI {
    on(event: "tool_call", handler: (event: ToolCallEvent, ctx: ExtensionContext) => Promise<unknown> | unknown): void;
    on(event: "tool_result", handler: (event: ToolResultEvent) => Promise<void> | void): void;
    on(event: "session_start", handler: (event: unknown, ctx: ExtensionContext) => Promise<void> | void): void;
    on(event: "before_agent_start", handler: (event: AgentStartEvent) => Promise<void> | void): void;
    registerCommand(
      name: string,
      definition: { description: string; handler: (args: string[], ctx: ExtensionContext) => Promise<void> | void },
    ): void;
    appendEntry(customType: string, data: Record<string, unknown>): void;
    logger: { warn(message: string): void };
  }
}
