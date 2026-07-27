import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../lib/api';
import type { Profile } from '../lib/types';

const STORAGE_KEY = 'kotoba.profileId';

interface ProfileContextValue {
  profiles: Profile[];
  currentProfile: Profile | null;
  loading: boolean;
  selectProfile: (id: number) => void;
  clearProfile: () => void;
  refreshProfiles: () => Promise<void>;
}

const ProfileContext = createContext<ProfileContextValue | null>(null);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [currentProfileId, setCurrentProfileId] = useState<number | null>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? Number(stored) : null;
  });
  const [loading, setLoading] = useState(true);

  const refreshProfiles = useCallback(async () => {
    const list = await api.listProfiles();
    setProfiles(list);
  }, []);

  useEffect(() => {
    refreshProfiles().finally(() => setLoading(false));
  }, [refreshProfiles]);

  const selectProfile = useCallback((id: number) => {
    localStorage.setItem(STORAGE_KEY, String(id));
    setCurrentProfileId(id);
  }, []);

  const clearProfile = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setCurrentProfileId(null);
  }, []);

  const currentProfile = useMemo(
    () => profiles.find((p) => p.id === currentProfileId) ?? null,
    [profiles, currentProfileId],
  );

  return (
    <ProfileContext.Provider
      value={{ profiles, currentProfile, loading, selectProfile, clearProfile, refreshProfiles }}
    >
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfiles() {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error('useProfiles must be used within a ProfileProvider');
  return ctx;
}
