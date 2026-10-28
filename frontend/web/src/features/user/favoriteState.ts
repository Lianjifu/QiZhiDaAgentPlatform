/**
 * 收藏列表的本地状态更新 —— 5 个用户侧页面共用。
 *
 * **为什么是「设置」而不是「切换」**:收藏要走后端,本地状态只能等服务端回话
 * 才更新。连点两个不同的条目时,两次 mutation 会重叠 —— React Query v5 的
 * observer 换人会把先发那次调用的回调丢掉,所以这里不能依赖
 * `mutate(vars, { onSuccess })` 里的回调,得让每次调用各自持有自己的
 * 结果(用 `mutateAsync`)。
 *
 * 就算两次都回来了,「切换」语义也会把同一个条目翻回去;「设置」语义是
 * 幂等的 —— 目标状态是什么就写成什么。
 */
export function applyFavorite(current: string[], id: string, on: boolean): string[] {
  if (on) return current.includes(id) ? current : [...current, id];
  return current.filter((item) => item !== id);
}
