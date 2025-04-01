const express = require('express');
const app = express();
const port = parseInt(process.env.PORT || "10000");

console.log(`PORT environment variable value: ${process.env.PORT}`);
console.log(`Using port: ${port}`);

app.get('/', (req, res) => {
  res.send('Hello World!')
});

app.get('/health', (req, res) => {
  res.json({ status: 'healthy', port: port });
});

app.listen(port, '0.0.0.0', () => {
  console.log(`App listening on port ${port}`)
}); 