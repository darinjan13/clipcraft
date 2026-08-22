import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test } from 'vitest';
import { useVideoStore } from '@/features/videos/store/useVideoStore';
import { GenerateForm } from './GenerateForm';

function renderForm() {
  return render(
    <GenerateForm
      onSubmit={() => undefined}
      loading={false}
      textModels={[]}
      imageModels={[]}
      modelsLoading={false}
      onRetryModels={() => undefined}
      providers={[]}
    />,
  );
}

describe('GenerateForm voice source', () => {
  beforeEach(() => useVideoStore.getState().resetDraft());

  test('keeps automatic voice selection and explains flexible duration', () => {
    renderForm();

    expect(screen.getAllByLabelText('Voice')).toHaveLength(1);
    expect(screen.getByText(/final duration may be slightly longer/i)).toBeInTheDocument();
  });

  test('maps Third-Party TTS to custom audio and only exposes narration export style', () => {
    renderForm();

    fireEvent.change(screen.getByLabelText('Voice source'), { target: { value: 'custom_audio' } });

    expect(useVideoStore.getState().draft.audio_mode).toBe('custom_audio');
    expect(screen.getByLabelText('Narration Export Style')).toHaveValue('clean');
    expect(screen.queryByLabelText('Voice')).not.toBeInTheDocument();
    expect(screen.queryByText(/final duration may be slightly longer/i)).not.toBeInTheDocument();
  });
});
