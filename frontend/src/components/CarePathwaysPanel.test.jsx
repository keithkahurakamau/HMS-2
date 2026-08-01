import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CarePathwaysPanel from './CarePathwaysPanel';
import { apiClient } from '../api/client';

vi.mock('../api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));
vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

const patient = { patient_id: 7, patient_name: 'Otieno, Sam' };

describe('CarePathwaysPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders nothing without the relevant permissions', () => {
    const { container } = render(<CarePathwaysPanel patient={patient} perms={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('requests a theatre case with the patient id and diagnosis', async () => {
    apiClient.post.mockResolvedValue({ data: {} });
    const user = userEvent.setup();
    render(<CarePathwaysPanel patient={patient} perms={['theatre:manage']} diagnosis="Appendicitis" />);

    await user.click(screen.getByRole('button', { name: /Request theatre/i }));
    await user.type(screen.getByLabelText('Procedure'), 'Appendectomy');
    await user.click(screen.getByRole('button', { name: /^Request$/i }));

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      '/theatre/cases', expect.objectContaining({
        patient_id: 7, procedure_name: 'Appendectomy', diagnosis: 'Appendicitis' })));
  });

  it('admits the patient to a chosen available bed', async () => {
    apiClient.get.mockResolvedValue({ data: [
      { id: 1, name: 'Male Ward', beds: [
        { id: 11, number: 'B1', status: 'Available' },
        { id: 12, number: 'B2', status: 'Occupied' }] }] });
    apiClient.post.mockResolvedValue({ data: {} });
    const user = userEvent.setup();
    render(<CarePathwaysPanel patient={patient} perms={['wards:read']} diagnosis="Pneumonia" />);

    await user.click(screen.getByRole('button', { name: /Admit patient/i }));
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/wards/board'));
    await user.selectOptions(await screen.findByLabelText('Ward'), '1');
    await user.selectOptions(screen.getByLabelText('Bed'), '11');
    await user.click(screen.getByRole('button', { name: /^Admit$/i }));

    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      '/wards/admit', { patient_id: 7, bed_id: 11, diagnosis: 'Pneumonia' }));
  });
});
