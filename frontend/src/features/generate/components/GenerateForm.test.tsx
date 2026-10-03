import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, test } from 'vitest';
import { useVideoStore } from '@/features/videos/store/useVideoStore';
import { GenerateForm } from './GenerateForm';

function renderForm() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <GenerateForm
        onSubmit={() => undefined}
        loading={false}
        textModels={[]}
        imageModels={[]}
        modelsLoading={false}
        onRetryModels={() => undefined}
        providers={[]}
      />
    </QueryClientProvider>,
  );
}

describe('GenerateForm voice source', () => {
  beforeEach(() => useVideoStore.getState().resetDraft());

  test('shows voice and gender pickers for automatic narration', () => {
    renderForm();

    expect(screen.getByLabelText('Voice')).toBeInTheDocument();
    expect(screen.getByLabelText('Gender')).toBeInTheDocument();
    expect(screen.getByLabelText('Voice source')).toHaveValue('automatic');
    expect(screen.queryByLabelText('Narration Export Style')).not.toBeInTheDocument();
  });

  test('maps Third-Party TTS to custom audio and only exposes narration export style', () => {
    renderForm();

    fireEvent.change(screen.getByLabelText('Voice source'), { target: { value: 'custom_audio' } });

    expect(useVideoStore.getState().draft.audio_mode).toBe('custom_audio');
    expect(screen.getByLabelText('Narration Export Style')).toHaveValue('clean');
    expect(screen.queryByLabelText('Voice')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Gender')).not.toBeInTheDocument();
  });
});
