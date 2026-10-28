/**
 * applyFavorite —— 收藏列表的本地状态更新。
 *
 * 语义是「设置」不是「切换」:目标状态是什么就写成什么,重复调用幂等。
 */
import { describe, expect, it } from 'vitest';
import { applyFavorite } from './favoriteState';

describe('applyFavorite', () => {
  it('加上未收藏的条目', () => {
    expect(applyFavorite([], 'a', true)).toEqual(['a']);
  });

  it('已收藏时保持原样(幂等)', () => {
    const current = ['a'];
    expect(applyFavorite(current, 'a', true)).toBe(current);
  });

  it('移除已收藏的条目', () => {
    expect(applyFavorite(['a', 'b'], 'a', false)).toEqual(['b']);
  });

  it('未收藏时移除是空操作', () => {
    expect(applyFavorite(['b'], 'a', false)).toEqual(['b']);
  });
});
