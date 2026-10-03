import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:test', writable: true });
Object.defineProperty(URL, 'revokeObjectURL', { value: () => undefined, writable: true });

afterEach(cleanup);
