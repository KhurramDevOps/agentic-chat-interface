import api from './axiosInstance';

export const uploadFileApi = (file) => {
  const formData = new FormData();
  formData.append('file', file);

  return api
    .post('/api/files/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((response) => response.data);
};
