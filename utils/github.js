const axios = require('axios');

const githubAPI = axios.create({
  baseURL: 'https://api.github.com',
  headers: {
    'Accept': 'application/vnd.github.v3+json'
  }
});

// ============ FETCH REPOSITORIES ============
const fetchRepositories = async (token) => {
  try {
    const response = await githubAPI.get('/user/repos', {
      headers: { Authorization: `Bearer ${token}` },
      params: {
        per_page: 100,
        sort: 'updated',
        direction: 'desc'
      }
    });
    return response.data;
  } catch (error) {
    console.error('Error fetching repositories:', error.message);
    throw error;
  }
};

// ============ FETCH ISSUES ============
const fetchIssues = async (token) => {
  try {
    const response = await githubAPI.get('/user/issues', {
      headers: { Authorization: `Bearer ${token}` },
      params: {
        per_page: 100,
        state: 'all',
        sort: 'updated'
      }
    });
    return response.data;
  } catch (error) {
    console.error('Error fetching issues:', error.message);
    throw error;
  }
};

// ============ FETCH PULL REQUESTS ============
const fetchPullRequests = async (token) => {
  try {
    const response = await githubAPI.get('/user/pulls', {
      headers: { Authorization: `Bearer ${token}` },
      params: {
        per_page: 100,
        state: 'all',
        sort: 'updated'
      }
    });
    return response.data;
  } catch (error) {
    console.error('Error fetching pull requests:', error.message);
    throw error;
  }
};

// ============ GET USER PROFILE ============
const getUserProfile = async (token) => {
  try {
    const response = await githubAPI.get('/user', {
      headers: { Authorization: `Bearer ${token}` }
    });
    return response.data;
  } catch (error) {
    console.error('Error fetching user profile:', error.message);
    throw error;
  }
};

// ============ EXCHANGE CODE FOR TOKEN ============
const exchangeCodeForToken = async (code) => {
  try {
    const response = await axios.post(
      'https://github.com/login/oauth/access_token',
      {
        client_id: process.env.GITHUB_CLIENT_ID,
        client_secret: process.env.GITHUB_CLIENT_SECRET,
        code: code
      },
      { headers: { Accept: 'application/json' } }
    );

    if (response.data.error) {
      throw new Error(response.data.error_description);
    }

    return response.data.access_token;
  } catch (error) {
    console.error('Error exchanging code for token:', error.message);
    throw error;
  }
};

module.exports = {
  fetchRepositories,
  fetchIssues,
  fetchPullRequests,
  getUserProfile,
  exchangeCodeForToken
};
