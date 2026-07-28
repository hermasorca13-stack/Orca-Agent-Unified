const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const dotenv = require('dotenv');
const path = require('path');

// Load environment variables
dotenv.config();

const app = express();

// ============ MIDDLEWARE ============
app.use(helmet()); // Security headers
app.use(cors({ 
  origin: process.env.CORS_ORIGIN || 'http://localhost:3000',
  credentials: true 
}));
app.use(morgan('combined')); // Logging
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));

// ============ ROUTES ============
const authRoutes = require('./routes/auth');
const syncRoutes = require('./routes/sync');
const webhookRoutes = require('./routes/webhooks');
const userRoutes = require('./routes/users');
const aiRoutes = require('./routes/ai');

app.use('/api/auth', authRoutes);
app.use('/api/sync', syncRoutes);
app.use('/api/webhooks', webhookRoutes);
app.use('/api/users', userRoutes);
app.use('/api/ai', aiRoutes);

// ============ HEALTH CHECK ============
app.get('/api/health', (req, res) => {
  res.json({
    status: 'operational',
    timestamp: new Date(),
    uptime: process.uptime()
  });
});

// ============ ERROR HANDLING ============
app.use((err, req, res, next) => {
  console.error(err);
  res.status(err.status || 500).json({
    error: err.message || 'Internal Server Error',
    timestamp: new Date()
  });
});

// ============ 404 HANDLER ============
app.use((req, res) => {
  res.status(404).json({ error: 'Route not found' });
});

// ============ START SERVER ============
const PORT = process.env.APP_PORT || 3000;
app.listen(PORT, () => {
  console.log(`\n✅ Orca Agent - GitHub Manus Bridge`);
  console.log(`📡 Server running on http://localhost:${PORT}`);
  console.log(`🔐 Environment: ${process.env.NODE_ENV}`);
  console.log(`\n🚀 Ready to integrate GitHub with Manus!\n`);
});

module.exports = app;
