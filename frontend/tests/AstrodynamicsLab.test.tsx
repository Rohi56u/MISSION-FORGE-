import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { AstrodynamicsLab } from '../src/views/AstrodynamicsLab';
import { api } from '../src/lib/api';

describe('AstrodynamicsLab View Integration', () => {
  it('mounts porkchop plot and 3D trajectory view', async () => {
    vi.spyOn(api, 'calculatePorkchop').mockReturnValue(new Promise(() => {}));
    vi.spyOn(api, 'solveLambert').mockReturnValue(new Promise(() => {}));

    render(<AstrodynamicsLab />);
    expect(screen.getByTestId('astrodynamics-lab-view')).toBeInTheDocument();
    expect(screen.getByTestId('porkchop-plot-section')).toBeInTheDocument();
    expect(screen.getByTestId('trajectory-3d-section')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByRole('note')).toBeInTheDocument();
    });
  });
});
