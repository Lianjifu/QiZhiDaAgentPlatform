import { describe, expect, it } from 'vitest';
import { defaultRouteForRole, pathAllowedForRole, resolvePostLoginRoute } from './roleRoutes';

describe('roleRoutes', () => {
  it('sends admin and member to different homes', () => {
    expect(defaultRouteForRole('admin')).toBe('/admin/overview');
    expect(defaultRouteForRole('user')).toBe('/home');
  });

  it('keeps admin out of the member workbench and members out of /admin', () => {
    expect(pathAllowedForRole('/home', 'admin')).toBe(false);
    expect(pathAllowedForRole('/admin/overview', 'user')).toBe(false);
    expect(pathAllowedForRole('/admin/overview', 'admin')).toBe(true);
    expect(pathAllowedForRole('/copilot', 'user')).toBe(true);
  });

  it('ignores a previous location that belongs to the other audience', () => {
    expect(resolvePostLoginRoute('admin', '/home')).toBe('/admin/overview');
    expect(resolvePostLoginRoute('user', '/admin/overview')).toBe('/home');
    expect(resolvePostLoginRoute('user', '/copilot')).toBe('/copilot');
  });
});
