/**
 * authStoreRef.js
 * ────────────────
 * Re-exports authStore so apiClient can import it lazily
 * without creating a circular dependency at module load time.
 */
import useAuthStore from '../store/authStore';

export default useAuthStore;
