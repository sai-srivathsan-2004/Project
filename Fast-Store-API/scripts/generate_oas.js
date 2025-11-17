const swaggerAutogen = require('swagger-autogen')();
const outputFile = './openapi.generated.json';
const endpointsFiles = ['./backend/index.js','./backend/app.js','./backend/server.js','./backend/routes/index.js'];
const doc = {
  info: { title: 'Fast-Store-API (generated)', description: 'Auto-generated OpenAPI' },
  host: 'localhost:3000',
  schemes: ['http']
};
swaggerAutogen(outputFile, endpointsFiles, doc).then(() => {
  console.log('swagger-autogen finished');
}).catch(e => { console.error(e); process.exit(1); });
