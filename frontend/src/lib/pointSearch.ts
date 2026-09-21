import type { CoverageTree } from "@/lib/types";

/** 覆盖树搜索：命中考点名，或命中子模块名/科目名（整块视为命中）。 */
export interface TreeSearchResult {
  active: boolean;
  points: Set<string>;    // 命中的考点名（选择器按名字勾选，跨子模块同名同选）
  subjects: Set<string>;  // 需要展示/展开的科目
  subs: Set<string>;      // 需要展示/展开的子模块，键为 `${subject}\u0000${sub}`
  total: number;
}

export function normKeyword(text: string): string {
  return (text || "").replace(/[\s\u3000]+/g, "").toLowerCase();
}

export function matchesKeyword(keyword: string, text: string): boolean {
  const kw = normKeyword(keyword);
  return kw.length > 0 && normKeyword(text).includes(kw);
}

export function subKey(subject: string, sub: string): string {
  return `${subject}\u0000${sub}`;
}

export function searchTree(tree: CoverageTree, keyword: string): TreeSearchResult {
  const kw = normKeyword(keyword);
  const result: TreeSearchResult = {
    active: kw.length > 0,
    points: new Set<string>(),
    subjects: new Set<string>(),
    subs: new Set<string>(),
    total: 0,
  };
  if (!kw) return result;
  for (const [subject, sdata] of Object.entries(tree)) {
    const subjectHit = normKeyword(subject).includes(kw);
    for (const [sub, subdata] of Object.entries(sdata.submodules)) {
      const subHit = subjectHit || normKeyword(sub).includes(kw);
      const hitPoints = Object.keys(subdata.points)
        .filter((point) => subHit || normKeyword(point).includes(kw));
      if (hitPoints.length === 0) continue;
      result.subjects.add(subject);
      result.subs.add(subKey(subject, sub));
      hitPoints.forEach((point) => result.points.add(point));
      result.total += hitPoints.length;
    }
  }
  return result;
}
