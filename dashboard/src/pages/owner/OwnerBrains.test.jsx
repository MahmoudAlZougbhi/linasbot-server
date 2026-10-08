import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OwnerBrains from './OwnerBrains';
import { ownerApi } from './ownerApi';

vi.mock('./ownerApi', () => ({
  ownerApi: {
    subscribers: vi.fn(),
    brainTurn: vi.fn(),
  },
}));

const subscribers = /** @type {import('vitest').Mock} */ (ownerApi.subscribers);
const brainTurn = /** @type {import('vitest').Mock} */ (ownerApi.brainTurn);

function renderBrains() {
  return render(
    <MemoryRouter>
      <OwnerBrains />
    </MemoryRouter>,
  );
}

describe('OwnerBrains', () => {
  beforeEach(() => {
    subscribers.mockResolvedValue({
      subscribers: [
        { tenant_id: 'shop-a', business_name: 'Shop A', email: 'a@example.com' },
        { tenant_id: 'shop-b', business_name: 'Shop B', email: 'b@example.com' },
      ],
    });
    brainTurn.mockResolvedValue({ reply: 'أهلا من شوب أ', reason: '' });
  });

  it('sends the selected tenant to the customer brain and clears the thread on switch', async () => {
    renderBrains();
    const tenant = await screen.findByLabelText('Business');
    expect(tenant).toHaveValue('shop-a');
    fireEvent.change(screen.getByLabelText('Message Customer AI'), { target: { value: 'بدي سعر' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send to Customer AI' }));
    await waitFor(() => expect(screen.getByText('أهلا من شوب أ')).toBeInTheDocument());
    expect(brainTurn).toHaveBeenCalledWith('customer', {
      tenant_id: 'shop-a',
      message: 'بدي سعر',
      history: [],
      mode: 'live',
    });
    fireEvent.change(tenant, { target: { value: 'shop-b' } });
    expect(screen.queryByText('أهلا من شوب أ')).not.toBeInTheDocument();
    expect(screen.queryByText('بدي سعر')).not.toBeInTheDocument();
  });

  it('shows the owner copilot empty text', async () => {
    renderBrains();
    await screen.findByLabelText('Business');
    fireEvent.click(screen.getByRole('tab', { name: 'Owner Copilot' }));
    expect(screen.getByText('Ask like the business owner would')).toBeInTheDocument();
  });
});
