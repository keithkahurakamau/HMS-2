import axios from 'axios';

export const apiClient = axios.create({
    baseURL: 'http://127.0.0.1:8000/api',
    withCredentials: true, // CRITICAL: This ensures the secure cookies are sent with every request
    headers: {
        'Content-Type': 'application/json',
    }
});