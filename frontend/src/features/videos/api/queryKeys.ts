export const videoKeys = { all: ['videos'] as const, detail: (id: string) => ['videos', id] as const, status: (id: string) => ['videos', id, 'status'] as const };
