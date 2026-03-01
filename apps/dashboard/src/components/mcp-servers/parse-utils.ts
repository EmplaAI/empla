/**
 * Shared parsing utilities for MCP server form data.
 */

/** Split a command string on whitespace, respecting quoted strings. */
export function parseCommand(raw: string | undefined): string[] | undefined {
  if (!raw?.trim()) return undefined;
  const parts: string[] = [];
  let current = '';
  let inQuote = false;
  let quoteChar = '';
  for (const ch of raw) {
    if (inQuote) {
      if (ch === quoteChar) {
        inQuote = false;
      } else {
        current += ch;
      }
    } else if (ch === '"' || ch === "'") {
      inQuote = true;
      quoteChar = ch;
    } else if (ch === ' ' || ch === '\t') {
      if (current) {
        parts.push(current);
        current = '';
      }
    } else {
      current += ch;
    }
  }
  if (current) parts.push(current);
  return parts.length > 0 ? parts : undefined;
}

/** Build credentials payload from form data based on auth type. */
export function buildCredentials(
  authType: string,
  fields: {
    apiKey?: string;
    bearerToken?: string;
    oauthClientId?: string;
    oauthClientSecret?: string;
    oauthTokenUrl?: string;
    oauthAuthorizationUrl?: string;
    oauthScopes?: string;
  },
): Record<string, unknown> | undefined {
  if (authType === 'api_key' && fields.apiKey) return { api_key: fields.apiKey };
  if (authType === 'bearer_token' && fields.bearerToken) return { token: fields.bearerToken };
  if (authType === 'oauth' && fields.oauthClientId)
    return {
      client_id: fields.oauthClientId,
      client_secret: fields.oauthClientSecret,
      token_url: fields.oauthTokenUrl,
      authorization_url: fields.oauthAuthorizationUrl,
      scopes: fields.oauthScopes
        ?.split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    };
  return undefined;
}

/** Parse KEY=value lines into a Record. */
export function parseEnv(raw: string | undefined): Record<string, string> | undefined {
  if (!raw?.trim()) return undefined;
  const env: Record<string, string> = {};
  for (const line of raw.split('\n')) {
    const eq = line.indexOf('=');
    if (eq > 0) {
      env[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
    }
  }
  return Object.keys(env).length > 0 ? env : undefined;
}
