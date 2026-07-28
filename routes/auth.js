const express = require('express');
const jwt = require('jsonwebtoken');
const crypto = require('crypto');
const router = express.Router();

const githubUtils = require('../utils/github');
const manusUtils = require('../utils/manus');
const User = require('../models/User');

// ============ 1. INITIATE GITHUB LOGIN ============
router.get('/login/github', (req, res) => {
  const redirectUri = encodeURIComponent(
    `${process.env.APP_URL}/api/auth/github/callback`
  );
  const scope = 'user:email%20repo%20read:org';
  const state = crypto.randomBytes(16).toString('hex');

  // Store state in session (in production, use Redis or session store)
  req.session = req.session || {};
  req.session.oauthState = state;

  const githubAuthUrl =
    `https://github.com/login/oauth/authorize?` +
    `client_id=${process.env.GITHUB_CLIENT_ID}&` +
    `redirect_uri=${redirectUri}&` +
    `scope=${scope}&` +
    `state=${state}`;

  res.redirect(githubAuthUrl);
});

// ============ 2. GITHUB OAUTH CALLBACK ============
router.get('/github/callback', async (req, res) => {
  const { code, state, error } = req.query;

  if (error) {
    return res.status(400).json({ 
      error: 'GitHub authorization denied',
      details: error 
    });
  }

  if (!code) {
    return res.status(400).json({ error: 'No authorization code received' });
  }

  try {
    // Validate state (security measure)
    // if (state !== req.session?.oauthState) {
    //   return res.status(400).json({ error: 'Invalid state parameter' });
    // }

    // Step 1: Exchange code for GitHub token
    const githubToken = await githubUtils.exchangeCodeForToken(code);

    // Step 2: Get GitHub user profile
    const githubUser = await githubUtils.getUserProfile(githubToken);

    // Step 3: Check if user exists in database
    let user = await User.findOne({ githubId: githubUser.id });

    if (!user) {
      // Step 4: Link to Manus (new user)
      const manusUser = await manusUtils.linkUserToManus(githubUser, githubToken);

      // Step 5: Create new user in database
      user = new User({
        githubId: githubUser.id,
        githubLogin: githubUser.login,
        githubToken: githubToken,
        manusId: manusUser.id,
        email: githubUser.email,
        profile: {
          name: githubUser.name,
          avatar: githubUser.avatar_url,
          bio: githubUser.bio,
          company: githubUser.company,
          location: githubUser.location,
          blog: githubUser.blog,
          publicRepos: githubUser.public_repos
        }
      });

      await user.save();
      console.log(`✅ New user created: ${githubUser.login}`);
    } else {
      // Update existing user
      user.githubToken = githubToken;
      user.profile = {
        name: githubUser.name,
        avatar: githubUser.avatar_url,
        bio: githubUser.bio,
        company: githubUser.company,
        location: githubUser.location,
        blog: githubUser.blog,
        publicRepos: githubUser.public_repos
      };
      await user.save();
      console.log(`✅ User updated: ${githubUser.login}`);
    }

    // Step 6: Create JWT token
    const jwtToken = jwt.sign(
      {
        userId: user._id,
        githubId: user.githubId,
        githubLogin: user.githubLogin,
        manusId: user.manusId,
        email: user.email
      },
      process.env.JWT_SECRET,
      { expiresIn: process.env.JWT_EXPIRY || '7d' }
    );

    // Step 7: Redirect to frontend with token
    const frontendURL = `${process.env.APP_URL}?token=${jwtToken}&user=${user.githubLogin}`;
    res.redirect(frontendURL);

  } catch (error) {
    console.error('❌ OAuth Error:', error);
    res.status(500).json({
      error: 'Authentication failed',
      message: error.message
    });
  }
});

// ============ 3. LOGOUT ============
router.post('/logout', (req, res) => {
  res.json({ message: 'Logged out successfully' });
});

// ============ 4. VERIFY TOKEN ============
router.get('/verify', (req, res) => {
  const token = req.headers.authorization?.split(' ')[1];

  if (!token) {
    return res.status(401).json({ error: 'No token provided' });
  }

  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    res.json({ valid: true, user: decoded });
  } catch (error) {
    res.status(401).json({ error: 'Invalid or expired token' });
  }
});

module.exports = router;
