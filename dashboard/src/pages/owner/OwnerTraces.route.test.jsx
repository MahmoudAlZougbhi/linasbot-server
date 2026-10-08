import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import CustomerMessages from './CustomerMessages';

vi.mock('./ownerApi', () => ({
  ownerApi: {
    subscribers: vi.fn(async () => ({ subscribers: [] })),
    messageFlows: vi.fn(async () => ({ messages: [] })),
    listTraces: vi.fn(async () => ({ traces: [] })),
  },
}));

describe('AI traces route', () => {
  it('selects the AI traces tab', async () => {
    render(
      <MemoryRouter initialEntries={['/owner/traces']}>
        <Routes>
          <Route path="/owner/traces" element={<CustomerMessages />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole('tab', { name: 'AI traces' })).toHaveAttribute('aria-selected', 'true');
  });
});
