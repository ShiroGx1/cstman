import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { requirePeers } from './peers.mjs';

// Every subpath in the package's `exports` map must import and expose the names
// the README tells people to call. Framework peers are optional, so a missing
// one skips rather than fails.
const ADAPTERS = {
  'ai-sdk': ['withCSTMAN', 'createCstmanMiddleware'],
  openai: ['withCstmanOpenAI', 'withCstmanOpenAITools', 'createCstmanFetch'],
  anthropic: ['withCstmanAnthropic'],
  google: ['CSTMANGoogleGenAI'],
  langchain: ['withCstmanAgent', 'withCstmanModel', 'CSTMANChatModel', 'scopeFromConfig', 'CSTMANDocumentCompressor', 'createCstmanLangChain'],
  strands: ['withCstmanStrands', 'withCstmanStrandsModel', 'CSTMANStrandsModel'],
  mastra: ['withCstmanMastra', 'createCstmanMastraProcessor'],
  mcp: ['CSTMANMCPHost', 'bindMCPTool'],
};

for (const [family, names] of Object.entries(ADAPTERS)) {
  test(`${family} exposes its documented entry points`, async t => {
    if (!requirePeers(t, family)) return;
    const module = await import(`../dist/${family}.js`);
    const missing = names.filter(name => typeof module[name] === 'undefined');
    assert.deepEqual(missing, [], `@cstman-ai/middleware/${family} lost ${missing}`);
  });
}

// C11: `@cstman-ai/middleware/langchain-model` needs only @langchain/core. A resolve hook makes `langchain`
// unresolvable in a child process: the model subpath still loads and runs, the full `langchain` subpath does not.
test('langchain-model loads and runs without langchain installed', async t => {
  if (!requirePeers(t, 'langchain')) return;
  const hooks = `export async function resolve(specifier, context, next) {
    if (specifier === 'langchain' || specifier.startsWith('langchain/')) throw Object.assign(new Error('blocked ' + specifier), { code: 'ERR_MODULE_NOT_FOUND' });
    return next(specifier, context);
  }`;
  const dist = name => JSON.stringify(new URL(`../dist/${name}.js`, import.meta.url).href);
  const script = `
    import assert from 'node:assert/strict';
    import { register } from 'node:module';
    register(${JSON.stringify(`data:text/javascript,${encodeURIComponent(hooks)}`)});
    await assert.rejects(import(${dist('langchain')}), { code: 'ERR_MODULE_NOT_FOUND' });
    const { withCstmanModel, CSTMANChatModel, CSTMANDocumentCompressor, scopeFromConfig } = await import(${dist('langchain-model')});
    assert.equal(typeof CSTMANChatModel, 'function'); assert.equal(typeof scopeFromConfig, 'function');
    const { createMiddlewareRuntime } = await import('@cstman-ai/sdk/middleware'), { FakeListChatModel } = await import('@langchain/core/utils/testing');
    const runtime = createMiddlewareRuntime({ mode: 'off' });
    const model = withCstmanModel(new FakeListChatModel({ responses: ['done'] }), { runtime, scope: { namespace: 'test', session_id: 'one' } });
    assert.equal((await model.invoke('hello')).content, 'done');
    const { Document } = await import('@langchain/core/documents'), documents = [new Document({ pageContent: 'kept' })];
    const compressor = new CSTMANDocumentCompressor({ runtime, scope: { namespace: 'test', session_id: 'one' } });
    assert.equal(await compressor.compressDocuments(documents, 'query'), documents); runtime.close();
  `;
  await promisify(execFile)(process.execPath, ['--input-type=module', '-e', script], { cwd: fileURLToPath(new URL('../', import.meta.url)) });
});
