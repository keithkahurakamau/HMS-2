import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import LaborBoardTab from './LaborBoardTab';
import * as api from './api';

vi.mock('./api');

// Deferred promise helper so the test controls exactly when each
// getPartograph() call resolves, independent of call order.
function deferred() {
  let resolve;
  const promise = new Promise((res) => { resolve = res; });
  return { promise, resolve };
}

describe('LaborBoardTab', () => {
  beforeEach(() => {
    api.getLaborBoard.mockResolvedValue([
      { labor_admission_id: 1, patient_name: 'Achieng, Faith', latest: null },
      { labor_admission_id: 2, patient_name: 'Mwangi, Joy', latest: null },
    ]);
  });

  it('never shows the previous patient chart while the next one is still loading', async () => {
    const laborA = deferred();
    const laborB = deferred();
    api.getPartograph.mockImplementation((laborId) => {
      if (laborId === 1) return laborA.promise;
      if (laborId === 2) return laborB.promise;
      return Promise.reject(new Error('unexpected labor id'));
    });

    const user = userEvent.setup();
    render(<LaborBoardTab />);

    // Select labor A and let its chart resolve.
    await user.click(await screen.findByText('Achieng, Faith'));
    laborA.resolve({
      labor_admission_id: 1,
      active_labor_started_at: '2026-07-21T06:00:00Z',
      entries: [],
    });
    await waitFor(() =>
      expect(screen.getByRole('img', { name: /partograph chart/i })).toBeInTheDocument()
    );
    expect(screen.getByText(/Partograph — Achieng, Faith/)).toBeInTheDocument();

    // Select labor B; its fetch is still pending.
    await user.click(screen.getByText('Mwangi, Joy'));

    // The heading must flip to the newly selected patient immediately...
    expect(screen.getByText(/Partograph — Mwangi, Joy/)).toBeInTheDocument();
    // ...but A's stale chart must NOT still be on screen under B's name.
    expect(screen.queryByRole('img', { name: /partograph chart/i })).not.toBeInTheDocument();
    expect(screen.getByText(/loading/i)).toBeInTheDocument();

    // Now resolve B's fetch and confirm its chart appears.
    laborB.resolve({
      labor_admission_id: 2,
      active_labor_started_at: '2026-07-21T07:00:00Z',
      entries: [],
    });
    await waitFor(() =>
      expect(screen.getByRole('img', { name: /partograph chart/i })).toBeInTheDocument()
    );
    expect(screen.getByText(/Partograph — Mwangi, Joy/)).toBeInTheDocument();
  });
});
