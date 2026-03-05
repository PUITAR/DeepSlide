import axios from 'axios';

const apiOrigin = String(import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');
const baseURL = apiOrigin ? `${apiOrigin}/api/v1` : '/api/v1';

const client = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export default client;
