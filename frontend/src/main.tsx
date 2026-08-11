import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/ui/Toast';
import { AppRouter } from '@/app/router';
import '@/index.css';

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } });

createRoot(document.getElementById('root')!).render(<StrictMode><QueryClientProvider client={queryClient}><ToastProvider><BrowserRouter><AppRouter /></BrowserRouter></ToastProvider></QueryClientProvider></StrictMode>);
