/**
 * 管理侧技能页 IO 工具 — JSON/YAML 序列化、解析、构建草稿、浏览器下载触发。
 * 全部为纯函数,保持与原 AdminSkills.tsx 同等行为。
 */
import type {
  Skill, TemplateSeed, SchemaField, RiskLevel, SkillType, SkillProfile,
  SkillExportField, SkillExportFormat,
} from '../schema';

export interface ImportRow {
  name: string;
  status: 'ok' | 'duplicate' | 'missing';
  message?: string;
}

export function uid(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 8)}`;
}

export function buildSkillFromTemplate(template: TemplateSeed, name: string, owner: string): Skill {
  const id = uid('skill');
  return {
    id, name, description: template.description, type: template.type, owner,
    status: 'draft', version: 'draft', lastUpdate: '刚刚',
    calls: 0, successRate: 0, errorRate: 0, avgLatencyMs: 0, rating: 0,
    risk: template.risk, needConfirm: template.needConfirm,
    visibleScope: ['部门'], tags: [...template.tags], starred: false,
    inputSchema: template.inputExample.map((f) => ({ ...f })),
    outputSchema: template.outputExample.map((f) => ({ ...f })),
    versions: [],
    trend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    usedByAgents: [],
    auditLog: [{ time: '刚刚', actor: owner, action: '从模板加入草稿' }],
  };
}

export function buildSkillFromDraft(
  name: string,
  type: SkillType,
  description: string,
  owner: string,
  risk: RiskLevel,
  profile?: SkillProfile,
  inputSchema: SchemaField[] = [],
  outputSchema: SchemaField[] = [],
): Skill {
  return {
    id: uid('skill'), name, description, type, owner,
    status: 'draft', version: 'draft', lastUpdate: '刚刚',
    calls: 0, successRate: 0, errorRate: 0, avgLatencyMs: 0, rating: 0,
    risk, needConfirm: risk !== 'low',
    visibleScope: ['部门'], tags: [], starred: false,
    inputSchema, outputSchema, versions: [],
    trend: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    usedByAgents: [],
    auditLog: [{ time: '刚刚', actor: owner, action: '新建技能' }],
    runtime: profile && profile.kind === 'Skill' ? profile.runtime : undefined,
  };
}

export function skillToYaml(skill: Skill, fields: Record<SkillExportField, boolean>): string {
  const lines: string[] = [];
  const push = (key: string, value: unknown) => lines.push(`  ${key}: ${typeof value === 'string' ? `"${value}"` : JSON.stringify(value)}`);
  lines.push(`- id: "${skill.id}"`);
  lines.push(`  name: "${skill.name}"`);
  lines.push(`  type: "${skill.type}"`);
  if (fields.meta) {
    push('description', skill.description);
    push('owner', skill.owner);
    push('tags', skill.tags);
    push('visibleScope', skill.visibleScope);
    push('starred', skill.starred);
  }
  if (fields.schema) {
    push('inputSchema', skill.inputSchema);
    push('outputSchema', skill.outputSchema);
  }
  if (fields.permission) {
    push('risk', skill.risk);
    push('needConfirm', skill.needConfirm);
  }
  if (fields.version) {
    push('version', skill.version);
    push('versions', skill.versions);
  }
  return `${lines.join('\n')}\n`;
}

export function skillToJson(skill: Skill, fields: Record<SkillExportField, boolean>): Record<string, unknown> {
  const out: Record<string, unknown> = { id: skill.id, name: skill.name, type: skill.type };
  if (fields.meta) {
    out.description = skill.description;
    out.owner = skill.owner;
    out.tags = skill.tags;
    out.visibleScope = skill.visibleScope;
    out.starred = skill.starred;
  }
  if (fields.schema) {
    out.inputSchema = skill.inputSchema;
    out.outputSchema = skill.outputSchema;
  }
  if (fields.permission) {
    out.risk = skill.risk;
    out.needConfirm = skill.needConfirm;
  }
  if (fields.version) {
    out.version = skill.version;
    out.versions = skill.versions;
  }
  return out;
}

export function parseImportRows(text: string, format: SkillExportFormat, existing: Skill[]): ImportRow[] {
  if (format === 'json') {
    try {
      const data = JSON.parse(text);
      const arr: Array<Record<string, unknown>> = Array.isArray(data) ? data : [data];
      return arr.map((row) => validateImportRow(row, existing));
    } catch {
      return [{ name: '(无效 JSON)', status: 'missing', message: '无法解析 JSON 文件' }];
    }
  }
  // YAML 简化解析
  const blocks: ImportRow[] = [];
  const lines = text.split('\n');
  let current: Record<string, string> = {};
  let currentName = '(未命名)';
  for (const raw of lines) {
    if (raw.startsWith('- ')) {
      if (Object.keys(current).length > 0 || currentName !== '(未命名)') {
        blocks.push(validateImportRow(current, existing, currentName));
      }
      current = {};
      currentName = '(未命名)';
      const kv = raw.slice(2);
      const idx = kv.indexOf(':');
      if (idx > -1) {
        const k = kv.slice(0, idx).trim();
        const v = kv.slice(idx + 1).trim().replace(/^"|"$/g, '');
        if (k === 'name') currentName = v;
        else current[k] = v;
      }
    } else if (raw.startsWith('  ') && raw.includes(':')) {
      const kv = raw.trim();
      const idx = kv.indexOf(':');
      if (idx > -1) {
        const k = kv.slice(0, idx).trim();
        const v = kv.slice(idx + 1).trim().replace(/^"|"$/g, '');
        if (k === 'name') currentName = v;
        else current[k] = v;
      }
    }
  }
  if (Object.keys(current).length > 0 || currentName !== '(未命名)') {
    blocks.push(validateImportRow(current, existing, currentName));
  }
  return blocks.length > 0 ? blocks : [{ name: '(空文件)', status: 'missing', message: '未发现任何技能条目' }];
}

function validateImportRow(row: Record<string, unknown>, existing: Skill[], fallbackName?: string): ImportRow {
  const name = (typeof row.name === 'string' ? row.name : fallbackName) || '(未命名)';
  if (!name || name === '(未命名)') {
    return { name, status: 'missing', message: '缺少名称字段' };
  }
  if (existing.some((s) => s.name === name)) {
    return { name, status: 'duplicate', message: '已存在同名技能' };
  }
  if (!row.type) {
    return { name, status: 'missing', message: '缺少类型字段' };
  }
  return { name, status: 'ok' };
}

export function downloadBlob(blob: Blob, filename: string) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function triggerDownload(list: Skill[], format: SkillExportFormat, fields: Record<SkillExportField, boolean>, baseName: string) {
  const safeBase = baseName.replace(/\s+/g, '-').toLowerCase();
  if (format === 'json') {
    const payload = list.map((s) => skillToJson(s, fields));
    downloadBlob(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }), `${safeBase}.json`);
    return;
  }
  const payload = list.map((s) => skillToYaml(s, fields)).join('\n');
  downloadBlob(new Blob([payload], { type: 'text/yaml' }), `${safeBase}.yaml`);
}

export function parseSchemaJson(input: string): SchemaField[] {
  try {
    const parsed = JSON.parse(input);
    return Array.isArray(parsed) ? (parsed as SchemaField[]) : [];
  } catch {
    return [];
  }
}