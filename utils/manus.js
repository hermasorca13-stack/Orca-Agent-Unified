const axios = require('axios');

const manusAPI = axios.create({
  baseURL: process.env.MANUS_ENDPOINT || 'https://api.manus.com',
  headers: {
    'Content-Type': 'application/json'
  }
});

// ============ LINK USER TO MANUS ============
const linkUserToManus = async (githubUser, githubToken) => {
  try {
    const response = await manusAPI.post(
      '/v1/users/link',
      {
        source: 'github',
        sourceId: githubUser.id,
        sourceLogin: githubUser.login,
        email: githubUser.email,
        profile: {
          name: githubUser.name,
          avatar: githubUser.avatar_url,
          bio: githubUser.bio,
          company: githubUser.company,
          location: githubUser.location,
          blog: githubUser.blog,
          publicRepos: githubUser.public_repos
        },
        githubToken: githubToken
      },
      {
        headers: { 'Authorization': `Bearer ${process.env.MANUS_API_KEY}` }
      }
    );

    return response.data.user;
  } catch (error) {
    console.error('Error linking user to Manus:', error.message);
    throw error;
  }
};

// ============ SYNC DATA TO MANUS ============
const syncDataToManus = async (manusId, data) => {
  try {
    const response = await manusAPI.post(
      '/v1/sync/data',
      {
        manusId: manusId,
        data: data,
        timestamp: new Date()
      },
      {
        headers: { 'Authorization': `Bearer ${process.env.MANUS_API_KEY}` }
      }
    );

    return response.data;
  } catch (error) {
    console.error('Error syncing data to Manus:', error.message);
    throw error;
  }
};

// ============ POST EVENT TO MANUS ============
const postEventToManus = async (eventType, payload) => {
  try {
    const response = await manusAPI.post(
      '/v1/events/github',
      {
        eventType: eventType,
        payload: payload,
        receivedAt: new Date()
      },
      {
        headers: { 'Authorization': `Bearer ${process.env.MANUS_API_KEY}` }
      }
    );

    return response.data;
  } catch (error) {
    console.error('Error posting event to Manus:', error.message);
    throw error;
  }
};

// ============ GET USER FROM MANUS ============
const getManusUser = async (manusId) => {
  try {
    const response = await manusAPI.get(
      `/v1/users/${manusId}`,
      {
        headers: { 'Authorization': `Bearer ${process.env.MANUS_API_KEY}` }
      }
    );

    return response.data.user;
  } catch (error) {
    console.error('Error getting Manus user:', error.message);
    throw error;
  }
};

module.exports = {
  linkUserToManus,
  syncDataToManus,
  postEventToManus,
  getManusUser
};
