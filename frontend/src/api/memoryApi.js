import api from './axiosInstance';

export const getUsageApi = () =>
  api.get('/api/users/usage').then((response) => response.data);

export const getMemoriesApi = () =>
  getUsageApi();
