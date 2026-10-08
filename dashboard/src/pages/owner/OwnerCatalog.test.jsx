import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import OwnerCatalog from './OwnerCatalog';

vi.mock('./ownerApi', () => ({
  ownerApi: {
    messageCatalog: vi.fn(async () => ({
      catalog: {
        published: false,
        plans: [{ plan_id: 'max', intended_price_usd: 279, included_messages: 25000, faq_capacity: 40, checkout_ready: false }],
        topup_packs: [{ pack_id: 'messages_100', quantity: 100, usd: 10, product_id: '', sale_ready: false }],
        free: { included_messages: '', configured: {} },
        payment_readiness: {
          apple: { status: 'implemented' },
          google: { status: 'incomplete', blocker: 'google_iap_not_fully_implemented' },
          stripe: { status: 'retired_token_packs' },
          annual_offers: { status: 'unconfigured' },
          topup_packs: { status: 'unpriced' },
        },
      },
    })),
  },
}));

describe('OwnerCatalog', () => {
  it('renders five payment rows from the payload', async () => {
    render(<MemoryRouter><OwnerCatalog /></MemoryRouter>);
    expect(await screen.findByText('Apple App Store')).toBeInTheDocument();
    expect(screen.getByText('Google Play')).toBeInTheDocument();
    expect(screen.getByText('Stripe')).toBeInTheDocument();
    expect(screen.getByText('Annual offers')).toBeInTheDocument();
    expect(screen.getByText('Top-up packs')).toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.getByText('Not finished')).toBeInTheDocument();
    expect(screen.getByText('Google Play billing is not finished')).toBeInTheDocument();
    expect(screen.getByText('Not used')).toBeInTheDocument();
    expect(screen.getByText('Not set up')).toBeInTheDocument();
    expect(screen.getByText('No price yet')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/_/);
    expect(document.body.textContent).not.toMatch(/cutover/i);
  });
});
