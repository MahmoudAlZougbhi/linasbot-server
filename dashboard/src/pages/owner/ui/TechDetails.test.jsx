import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import TechDetails from './TechDetails';

describe('TechDetails', () => {
  it('is collapsed by default', () => {
    render(<TechDetails text="instagram_dm" />);
    expect(screen.getByText('instagram_dm').closest('details')).not.toHaveAttribute('open');
  });
});
