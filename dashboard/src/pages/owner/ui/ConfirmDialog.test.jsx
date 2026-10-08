import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ConfirmDialog from './ConfirmDialog';

describe('ConfirmDialog', () => {
  it('focuses cancel, closes on escape, and confirms', async () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(<ConfirmDialog title="Hide Clinic?" body="No data is deleted." confirmLabel="Hide business" onClose={onClose} onConfirm={onConfirm} />);
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Hide business' }));
    expect(onConfirm).toHaveBeenCalled();
  });
});
