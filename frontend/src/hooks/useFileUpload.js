import { useMutation } from '@tanstack/react-query';
import { uploadFileApi } from '../api/fileApi';

export function useFileUpload() {
  return useMutation({
    mutationFn: uploadFileApi,
  });
}
