import { create } from 'zustand';
import type { VideoDraft } from '../types';

type State = {
  draft: VideoDraft;
  touched: Partial<Record<keyof VideoDraft, true>>;
  setDraft: (draft: Partial<VideoDraft>) => void;
  initializeDraft: (draft: Partial<VideoDraft>) => void;
  resetDraft: () => void;
};
const initial: VideoDraft = { title: '', prompt: '', duration: '30', style: 'Cinematic', voice: 'Warm narrator', captions: 'Clean', aspectRatio: '9:16' };
export const useVideoStore = create<State>((set) => ({
  draft: initial,
  touched: {},
  setDraft: (draft) => set((state) => ({
    draft: { ...state.draft, ...draft },
    touched: { ...state.touched, ...Object.keys(draft).reduce((result, key) => ({ ...result, [key]: true }), {}) },
  })),
  initializeDraft: (draft) => set((state) => ({
    draft: Object.entries(draft).reduce((result, [key, value]) => {
      const field = key as keyof VideoDraft;
      return !state.touched[field] && (state.draft[field] === undefined || state.draft[field] === '') ? { ...result, [field]: value } : result;
    }, state.draft),
  })),
  resetDraft: () => set({ draft: initial, touched: {} }),
}));
