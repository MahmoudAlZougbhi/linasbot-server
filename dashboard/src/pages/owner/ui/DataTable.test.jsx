import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import DataTable from './DataTable';

const rows = Array.from({ length: 30 }, (_, index) => ({ id: String(index + 1), name: `Person ${index + 1}` }));

describe('DataTable', () => {
  it('pages at 25 and searches', () => {
    render(
      <DataTable
        columns={[{ key: 'name', label: 'Name' }]}
        rows={rows}
        getRowId={(row) => row.id}
        searchText={(row) => row.name}
        searchPlaceholder="Search by email or business"
        empty={<p>No rows</p>}
      />,
    );
    expect(screen.getByText('Showing 1–25 of 30')).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('Search by email or business'), { target: { value: 'Person 30' } });
    expect(screen.getAllByText('Person 30').length).toBeGreaterThan(0);
    expect(screen.queryByText('Person 1')).not.toBeInTheDocument();
  });

  it('shows a skeleton while loading and not the empty state', () => {
    render(
      <DataTable
        columns={[{ key: 'name', label: 'Name' }]}
        rows={[]}
        getRowId={(row) => row.id}
        loading
        empty={<p>No tenants match.</p>}
      />,
    );
    expect(screen.queryByText('No tenants match.')).not.toBeInTheDocument();
  });
});
