const apiKey = process.env.API_KEY;
const dbUrl = process.env['DATABASE_URL'];
const secret = process.env["JWT_SECRET"];

// Dynamic ref
const configKey = 'some_key';
const dynamic = process.env[configKey];

module.exports = { apiKey, dbUrl };
