import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { GeneratePage } from '@/features/generate/pages/GeneratePage';
import { LibraryPage } from '@/features/library/pages/LibraryPage';
import { PreviewPage } from '@/features/preview/pages/PreviewPage';
import { SettingsPage } from '@/features/settings/pages/SettingsPage';

export function AppRouter() { return <Routes><Route element={<AppShell />}><Route path="/generate" element={<GeneratePage />} /><Route path="/library" element={<LibraryPage />} /><Route path="/library/:videoId" element={<PreviewPage />} /><Route path="/settings" element={<SettingsPage />} /><Route path="*" element={<Navigate to="/generate" replace />} /></Route></Routes>; }
