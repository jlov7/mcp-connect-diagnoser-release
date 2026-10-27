import express from 'express';
import { createMcpExpressApp, hostHeaderValidation, originValidation, requireBearerAuth } from '@modelcontextprotocol/express';
import { McpServer, OAuthError } from '@modelcontextprotocol/server';
import { NodeStreamableHTTPServerTransport } from '@modelcontextprotocol/node';

const mode = process.argv[2];
if (!['factory', 'auth-first', 'security-first'].includes(mode)) throw new Error('unknown composition');
const auth = requireBearerAuth({
  verifier: { async verifyAccessToken(token) {
    if (token !== 'synthetic-sdk-token') throw new OAuthError('invalid_token', 'Synthetic token rejected');
    return { token, clientId: 'synthetic', scopes: ['mcp'], expiresAt: 4102444800, resource: 'http://127.0.0.1/mcp' };
  } },
  requiredScopes: ['mcp'], expectedResource: new URL('http://127.0.0.1/mcp'),
  resourceMetadataUrl: 'http://127.0.0.1/.well-known/oauth-protected-resource/mcp'
});
const app = mode === 'factory' ? createMcpExpressApp() : express();
if (mode !== 'factory') {
  const guards = [hostHeaderValidation(['127.0.0.1', 'localhost', '[::1]']),
    originValidation(['127.0.0.1', 'localhost', '[::1]'])];
  app.use(...(mode === 'auth-first' ? [auth, ...guards] : [...guards, auth]));
  app.use(express.json({ limit: 4096 }));
} else app.use(auth);
app.post('/mcp', async (req, res) => {
  const server = new McpServer({ name: 'sdk-repro', version: '1.0.0' });
  const transport = new NodeStreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
  res.on('close', () => { void transport.close(); void server.close(); });
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
});
// Keep malformed-JSON control errors native, but suppress Express stderr echoing request details.
app.set('env', 'test');
const listener = app.listen(0, '127.0.0.1', () => console.log(listener.address().port));
listener.requestTimeout = 3000;
listener.headersTimeout = 3000;
