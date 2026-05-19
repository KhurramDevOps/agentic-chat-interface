import { useQuery } from '@tanstack/react-query';
import { getMemoriesApi } from '../api/memoryApi';
import { useAuth } from './useAuth';

export function useMemory() {
  const { user } = useAuth();
  return useQuery({
    queryKey: [user?.id, 'memory'],
    queryFn: getMemoriesApi,
    enabled: !!user?.id,
    staleTime: 60000,
  });
}
