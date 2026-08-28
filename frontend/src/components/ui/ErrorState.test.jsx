import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import ErrorState from './ErrorState';

describe('ErrorState', () => {
    it('announces itself as an alert and shows the title', () => {
        render(<ErrorState title="Could not load patients" message="The server did not respond." />);
        expect(screen.getByRole('alert')).toHaveTextContent('Could not load patients');
        expect(screen.getByText('The server did not respond.')).toBeInTheDocument();
    });

    it('calls onRetry when the retry button is pressed', async () => {
        const onRetry = vi.fn();
        render(<ErrorState title="Could not load patients" onRetry={onRetry} />);
        await userEvent.click(screen.getByRole('button', { name: /try again/i }));
        expect(onRetry).toHaveBeenCalledOnce();
    });

    it('omits the retry button when no handler is given', () => {
        render(<ErrorState title="Could not load" message="You do not have access." />);
        expect(screen.queryByRole('button')).not.toBeInTheDocument();
    });
});
