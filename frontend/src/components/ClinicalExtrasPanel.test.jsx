import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ClinicalExtrasPanel from './ClinicalExtrasPanel';
import { apiClient } from '../api/client';

vi.mock('../api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));
vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

const patient = { patient_id: 7, patient_name: 'Otieno, Sam' };

describe('ClinicalExtrasPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders nothing without a patient', () => {
    const { container } = render(<ClinicalExtrasPanel patient={null} onApplyOrderSet={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('saves a sick note with the active patient id', async () => {
    apiClient.post.mockResolvedValue({ data: {} });
    const user = userEvent.setup();
    render(<ClinicalExtrasPanel patient={patient} onApplyOrderSet={() => {}} />);

    await user.click(screen.getByRole('button', { name: /Sick note/i }));
    await user.click(await screen.findByRole('button', { name: /^Save$/i }));

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      '/clinical-extras/sick-notes', expect.objectContaining({ patient_id: 7 })));
  });

  it('applies a chosen order set to the parent', async () => {
    apiClient.get.mockResolvedValue({ data: [
      { order_set_id: 3, name: 'Diabetes work-up', description: '', items: [
        { item_id: 1, item_type: 'Drug', name: 'Metformin', ref_code: null }] }] });
    const onApply = vi.fn();
    const user = userEvent.setup();
    render(<ClinicalExtrasPanel patient={patient} onApplyOrderSet={onApply} />);

    await user.click(screen.getByRole('button', { name: /Order sets/i }));
    await user.click(await screen.findByRole('button', { name: /^Apply$/i }));
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ order_set_id: 3 }));
  });
});
