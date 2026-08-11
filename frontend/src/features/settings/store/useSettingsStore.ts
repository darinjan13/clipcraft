import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type PersistedSettings = { defaultDuration: string; defaultStyle: string; reduceMotion: boolean; autoCaptions: boolean };
type Settings = PersistedSettings & { setSetting: <K extends keyof PersistedSettings>(key: K, value: PersistedSettings[K]) => void };
const defaults: PersistedSettings = { defaultDuration: '30', defaultStyle: 'Cinematic', reduceMotion: false, autoCaptions: true };
export const useSettingsStore = create<Settings>()(persist((set) => ({ ...defaults, setSetting: (key, value) => set({ [key]: value } as Partial<PersistedSettings>) }), { name: 'clipcraft-settings' }));
