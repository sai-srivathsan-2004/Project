// Fast-Store-API/backend/scripts/autodetect_generate_oas.js
// Auto-detect .js backend files and feed them to swagger-autogen

const glob = require('glob');
const swaggerAutogen = require('swagger-autogen')();

const allFiles = glob.sync('**/*.js', {
  ignore: ['node_modules/**', 'scripts/**', '**/*.test.js', '**/test/**']
});

// heuristics to prioritize common entry points
const prioritized = ['index.js','server.js','app.js','routes/index.js','routes.js'];
const chosen = [];

for (const p of prioritized) {
  const found = allFiles.find(f => f.endsWith(p));
  if (found) chosen.push(found);
}

for (const f of allFiles) {
  if (chosen.length >= 20) break;
  if (!chosen.includes(f) && /router|route|express|app|index|server/.test(f)) {
    chosen.push(f);
  }
}

if (chosen.length === 0) {
  const fallback = allFiles.find(f => f.endsWith('index.js'));
  if (fallback) chosen.push(fallback);
}

const endpointsFiles = chosen.map(p => './' + p);
const outputFile = './openapi.generated.json';
const doc = {
  info: { title: 'Fast-Store-API (Generated)', description: 'Auto-generated OAS' }
};

console.log('Detected endpoint files:', endpointsFiles);
swaggerAutogen(outputFile, endpointsFiles, doc)
  .then(() => console.log('swagger-autogen finished successfully'))
  .catch(e => console.error('swagger-autogen error:', e));
