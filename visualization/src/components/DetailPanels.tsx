import type {
  RoleLinkUnified,
  RoleNodeUnified,
  TimelineEventUnified,
  UnifiedKnowledgeBase,
  UnifiedLocation,
  UnifiedRelation,
} from '../types/unified';

function resolveRoleId(kb: UnifiedKnowledgeBase | null, nameOrId: string): string | null {
  if (!kb) return null;
  if (kb.roles?.[nameOrId]) return nameOrId;
  const fromIndex = kb.name_to_role_id?.[nameOrId];
  if (fromIndex && kb.roles?.[fromIndex]) return fromIndex;
  for (const role of Object.values(kb.roles ?? {})) {
    if (role.all_names?.includes(nameOrId)) return role.id;
  }
  return null;
}

function formatUnitSpan(units: number[] | undefined, unitLabel: string): string {
  if (!units || units.length === 0) return `未知${unitLabel}`;
  const sorted = [...units].sort((a, b) => a - b);
  const start = sorted[0];
  const end = sorted[sorted.length - 1];
  return start === end ? `${unitLabel}${start}` : `${unitLabel}${start}–${end}`;
}

function renderRoleChip(opts: {
  name: string;
  kb: UnifiedKnowledgeBase | null;
  availableRoleIds: Set<string>;
  onClick: (name: string) => void;
}) {
  const { name, kb, availableRoleIds, onClick } = opts;
  const unitLabel = kb?.unit_label ?? '章节';
  const roleId = resolveRoleId(kb, name);
  const available = roleId ? availableRoleIds.has(roleId) : false;
  const units = roleId
    ? kb?.roles?.[roleId]?.units_appeared ?? kb?.roles?.[roleId]?.juans_appeared
    : undefined;
  const unitSpan = formatUnitSpan(units, unitLabel);

  if (available) {
    return (
      <button
        key={name}
        onClick={() => onClick(name)}
        className="inline-flex items-center px-2 py-1 bg-[#faf8f5] border border-[#d4c5b5] rounded text-sm hover:bg-[#8b4513] hover:text-white hover:border-[#8b4513] transition-colors cursor-pointer"
      >
        {name}
      </button>
    );
  }

  return (
    <span
      key={name}
      className="inline-flex items-center px-2 py-1 bg-gray-100 border border-gray-300 rounded text-sm text-gray-400 cursor-not-allowed"
      title={`当前范围不可用。出现：${unitSpan}`}
    >
      {name}
      <span className="ml-1 text-[10px] text-gray-400">({unitSpan})</span>
    </span>
  );
}

interface EventDetailProps {
  event: TimelineEventUnified | null;
  onClose: () => void;
  onEntityClick?: (entityName: string) => void;
  onLocationClick?: (locationName: string) => void;
  kb: UnifiedKnowledgeBase | null;
  availableRoleIds: Set<string>;
}

export function EventDetail({ event, onClose, onEntityClick, onLocationClick, kb, availableRoleIds }: EventDetailProps) {
  if (!event) return null;

  const unitLabel = kb?.unit_label ?? '章节';
  const progressLabel = kb?.progress_label ?? '叙事进度';

  const handleEntityClick = (name: string) => {
    onClose();
    onEntityClick?.(name);
  };

  const handleLocationClick = (name: string) => {
    onClose();
    onLocationClick?.(name);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4 p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-xl font-bold text-[#8b4513]">{event.name}</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700 text-2xl leading-none">
            ×
          </button>
        </div>

        <div className="space-y-3">
          {(event.progressLabel || event.progressStart !== null) && (
            <div>
              <span className="font-semibold text-[#2c1810]">{progressLabel}：</span>
              <span className="text-gray-700">{event.progressLabel ?? event.progressStart}</span>
            </div>
          )}

          {event.timeText && (
            <div>
              <span className="font-semibold text-[#2c1810]">原文时间：</span>
              <span className="text-gray-700">{event.timeText}</span>
            </div>
          )}

          {event.location && (
            <div>
              <span className="font-semibold text-[#2c1810]">地点：</span>
              {onLocationClick ? (
                <button onClick={() => handleLocationClick(event.location!)} className="text-[#8b4513] hover:underline cursor-pointer">
                  {event.location}
                </button>
              ) : (
                <span className="text-gray-700">{event.location}</span>
              )}
            </div>
          )}

          {event.participants.length > 0 && (
            <div>
              <span className="font-semibold text-[#2c1810]">参与者：</span>
              <p className="text-xs text-gray-500 mt-0.5">点击可在关系图中查看</p>
              <div className="flex flex-wrap gap-2 mt-1">
                {event.participants.map((name) =>
                  renderRoleChip({ name, kb, availableRoleIds, onClick: handleEntityClick })
                )}
              </div>
            </div>
          )}

          <div>
            <span className="font-semibold text-[#2c1810]">描述：</span>
            <p className="text-gray-700 mt-1">{event.description}</p>
          </div>

          {event.background && (
            <div>
              <span className="font-semibold text-[#2c1810]">背景：</span>
              <p className="text-gray-700 mt-1">{event.background}</p>
            </div>
          )}

          {event.significance && (
            <div>
              <span className="font-semibold text-[#2c1810]">剧情意义：</span>
              <p className="text-gray-700 mt-1 text-sm italic">{event.significance}</p>
            </div>
          )}

          <div className="text-sm text-gray-500 pt-2 border-t border-[#d4c5b5]">
            来源：{unitLabel}{event.unitIndex}
          </div>
        </div>
      </div>
    </div>
  );
}

interface RoleDetailProps {
  role: RoleNodeUnified | null;
  onClose: () => void;
  onEntityClick?: (entityName: string) => void;
  onEventClick?: (event: TimelineEventUnified) => void;
  relatedEvents?: TimelineEventUnified[];
  kb: UnifiedKnowledgeBase | null;
  availableRoleIds: Set<string>;
}

export function RoleDetail({
  role,
  onClose,
  onEntityClick,
  onEventClick,
  relatedEvents,
  kb,
  availableRoleIds,
}: RoleDetailProps) {
  if (!role) return null;

  const unitLabel = kb?.unit_label ?? '章节';

  const handleEntityClick = (name: string) => {
    onClose();
    onEntityClick?.(name);
  };

  const handleEventClick = (event: TimelineEventUnified) => {
    onClose();
    onEventClick?.(event);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4 p-6 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-xl font-bold text-[#8b4513]">{role.name}</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700 text-2xl leading-none">
            ×
          </button>
        </div>

        <div className="space-y-3">
          {role.aliases.length > 0 && (
            <div>
              <span className="font-semibold text-[#2c1810]">别名：</span>
              <div className="flex flex-wrap gap-2 mt-1">
                {role.aliases.map((alias) => (
                  <span key={alias} className="px-2 py-1 bg-[#faf8f5] border border-[#d4a574] rounded text-sm text-[#8b4513]">
                    {alias}
                  </span>
                ))}
              </div>
            </div>
          )}

          {role.power && (
            <div>
              <span className="font-semibold text-[#2c1810]">阵营：</span>
              <span className="px-2 py-1 bg-[#c41e3a] text-white rounded text-sm ml-2">{role.power}</span>
            </div>
          )}

          <div>
            <span className="font-semibold text-[#2c1810]">简介：</span>
            <p className="text-gray-700 mt-1">{role.description || '暂无描述'}</p>
          </div>

          {role.relatedEntities.length > 0 && (
            <div>
              <span className="font-semibold text-[#2c1810]">相关人物：</span>
              <p className="text-xs text-gray-500 mt-0.5">点击可在图中查看</p>
              <div className="flex flex-wrap gap-2 mt-1">
                {role.relatedEntities.slice(0, 15).map((name) =>
                  renderRoleChip({ name, kb, availableRoleIds, onClick: handleEntityClick })
                )}
                {role.relatedEntities.length > 15 && (
                  <span className="text-sm text-gray-500 self-center">+{role.relatedEntities.length - 15}</span>
                )}
              </div>
            </div>
          )}

          {relatedEvents && relatedEvents.length > 0 && (
            <div>
              <span className="font-semibold text-[#2c1810]">相关事件：</span>
              <p className="text-xs text-gray-500 mt-0.5">点击可查看详情</p>
              <div className="mt-2 space-y-2 max-h-48 overflow-y-auto">
                {relatedEvents.slice(0, 10).map((event) => (
                  <button
                    key={event.id}
                    onClick={() => handleEventClick(event)}
                    className="w-full text-left p-2 bg-[#faf8f5] border border-[#d4c5b5] rounded hover:bg-[#8b4513] hover:text-white hover:border-[#8b4513] transition-colors"
                  >
                    <div className="font-medium text-sm">{event.name}</div>
                    <div className="text-xs opacity-70">{event.progressLabel ?? `进度 ${event.progressStart ?? '未知'}`}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <span className="font-semibold text-[#2c1810]">出现次数：</span>
            <span className="text-gray-700">{role.appearances} 次</span>
          </div>

          <div>
            <span className="font-semibold text-[#2c1810]">出现{unitLabel}：</span>
            <div className="flex flex-wrap gap-2 mt-1">
              {role.units.map((unit) => (
                <span key={unit} className="px-2 py-1 bg-[#faf8f5] border border-[#d4c5b5] rounded text-sm">
                  {unitLabel}{unit}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface LocationListProps {
  locations: UnifiedLocation[];
  onLocationClick?: (location: UnifiedLocation) => void;
}

export function LocationList({ locations, onLocationClick }: LocationListProps) {
  return (
    <div className="bg-white rounded-lg shadow-md p-4">
      <h3 className="text-lg font-bold text-[#2c1810] mb-4">地点列表</h3>
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {locations.map((location) => (
          <div
            key={location.id}
            className="p-3 border border-[#d4c5b5] rounded-lg hover:bg-[#faf8f5] cursor-pointer transition-colors"
            onClick={() => onLocationClick?.(location)}
          >
            <div className="flex justify-between items-start">
              <h4 className="font-semibold text-[#8b4513]">{location.canonical_name}</h4>
              {location.location_type && (
                <span className="text-xs px-2 py-1 bg-[#d4a574] text-white rounded">{location.location_type}</span>
              )}
            </div>
            {location.modern_name && <p className="text-sm text-gray-500 mt-1">今：{location.modern_name}</p>}
            {location.description && <p className="text-sm text-gray-700 mt-1 line-clamp-2">{location.description}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

interface LocationDetailProps {
  location: UnifiedLocation | null;
  relatedEvents: TimelineEventUnified[];
  relatedRoles: string[];
  relatedActions: UnifiedRelation[];
  onClose: () => void;
  onEntityClick?: (entityName: string) => void;
  onNavigateToMap?: () => void;
  kb: UnifiedKnowledgeBase | null;
  availableRoleIds: Set<string>;
}

export function LocationDetail({
  location,
  relatedEvents,
  relatedRoles,
  relatedActions,
  onClose,
  onEntityClick,
  onNavigateToMap,
  kb,
  availableRoleIds,
}: LocationDetailProps) {
  if (!location) return null;

  const handleEntityClick = (name: string) => {
    onClose();
    onEntityClick?.(name);
  };

  const unitLabel = kb?.unit_label ?? '章节';
  const units = location.units_appeared ?? location.juans_appeared;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 p-6 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-bold text-[#8b4513]">{location.canonical_name}</h2>
            {location.modern_name && <p className="text-sm text-gray-500">今：{location.modern_name}</p>}
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700 text-2xl leading-none">
            ×
          </button>
        </div>

        <div className="space-y-4">
          {location.location_type && (
            <div>
              <span className="font-semibold text-[#2c1810]">类型：</span>
              <span className="text-gray-700">{location.location_type}</span>
            </div>
          )}

          {location.description && (
            <div>
              <span className="font-semibold text-[#2c1810]">描述：</span>
              <p className="text-gray-700 mt-1">{location.description}</p>
            </div>
          )}

          {relatedRoles.length > 0 && (
            <div>
              <span className="font-semibold text-[#2c1810]">相关人物：</span>
              <div className="flex flex-wrap gap-2 mt-1">
                {relatedRoles.map((name) =>
                  renderRoleChip({ name, kb, availableRoleIds, onClick: handleEntityClick })
                )}
              </div>
            </div>
          )}

          {relatedEvents.length > 0 && (
            <div>
              <span className="font-semibold text-[#2c1810]">相关事件：</span>
              <div className="mt-2 space-y-2 max-h-48 overflow-y-auto">
                {relatedEvents.map((event) => (
                  <div key={event.id} className="rounded-lg border border-[#d4c5b5] bg-[#faf8f5] p-3">
                    <div className="font-medium text-[#2c1810]">{event.name}</div>
                    <div className="text-xs text-gray-500 mt-1">{event.progressLabel ?? `进度 ${event.progressStart ?? '未知'}`}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {relatedActions.length > 0 && (
            <div>
              <span className="font-semibold text-[#2c1810]">关联关系：</span>
              <div className="mt-2 space-y-2">
                {relatedActions.map((action) => (
                  <div key={action.id} className="rounded-lg border border-[#d4c5b5] bg-[#faf8f5] p-3 text-sm text-gray-700">
                    {action.from_entity} → {action.to_entity} · {action.primary_action}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <span className="font-semibold text-[#2c1810]">出现{unitLabel}：</span>
            <div className="flex flex-wrap gap-2 mt-1">
              {units.map((unit) => (
                <span key={unit} className="px-2 py-1 bg-[#faf8f5] border border-[#d4c5b5] rounded text-sm">
                  {unitLabel}{unit}
                </span>
              ))}
            </div>
          </div>

          {onNavigateToMap && (
            <button
              onClick={() => {
                onClose();
                onNavigateToMap();
              }}
              className="px-3 py-2 rounded-lg bg-[#8b4513] text-white hover:bg-[#5d2e0c] transition-colors"
            >
              在地点关系视图中查看
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

interface RelationDetailProps {
  relations: RoleLinkUnified[];
  sourceName: string;
  targetName: string;
  onClose: () => void;
  onEntityClick?: (entityName: string) => void;
  onEventClick?: (event: TimelineEventUnified) => void;
  relatedEvents?: TimelineEventUnified[];
  kb: UnifiedKnowledgeBase | null;
  availableRoleIds: Set<string>;
}

export function RelationDetail({
  relations,
  sourceName,
  targetName,
  onClose,
  onEntityClick,
  onEventClick,
  relatedEvents,
  kb,
  availableRoleIds,
}: RelationDetailProps) {
  const unitLabel = kb?.unit_label ?? '章节';
  const sourceId = resolveRoleId(kb, sourceName);
  const targetId = resolveRoleId(kb, targetName);
  const sourceAvailable = sourceId ? availableRoleIds.has(sourceId) : false;
  const targetAvailable = targetId ? availableRoleIds.has(targetId) : false;
  const sourceUnits = sourceId ? kb?.roles?.[sourceId]?.units_appeared ?? kb?.roles?.[sourceId]?.juans_appeared : [];
  const targetUnits = targetId ? kb?.roles?.[targetId]?.units_appeared ?? kb?.roles?.[targetId]?.juans_appeared : [];
  const allSourceUnits = [...new Set(relations.flatMap((relation) => relation.sourceUnits || []))].sort((a, b) => a - b);
  const totalWeight = relations.reduce((sum, relation) => sum + relation.weight, 0);
  const earliestProgress = relations
    .map((relation) => relation.progressStart)
    .filter((value): value is number => value !== null)
    .sort((a, b) => a - b)[0];

  const handleEntityClick = (name: string) => {
    onClose();
    onEntityClick?.(name);
  };

  const handleEventClick = (event: TimelineEventUnified) => {
    onClose();
    onEventClick?.(event);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 p-6 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-bold text-[#8b4513]">人物关系详情</h2>
            <p className="text-lg text-[#2c1810] mt-1">
              <button
                onClick={() => sourceAvailable && handleEntityClick(sourceName)}
                disabled={!sourceAvailable}
                className={sourceAvailable ? 'font-semibold hover:text-[#8b4513] hover:underline' : 'font-semibold text-gray-400'}
              >
                {sourceName}
              </button>
              <span className="mx-2 text-gray-500">⇄</span>
              <button
                onClick={() => targetAvailable && handleEntityClick(targetName)}
                disabled={!targetAvailable}
                className={targetAvailable ? 'font-semibold hover:text-[#8b4513] hover:underline' : 'font-semibold text-gray-400'}
              >
                {targetName}
              </button>
            </p>
            {(!sourceAvailable || !targetAvailable) && (
              <p className="text-xs text-gray-400 mt-1">
                {!sourceAvailable ? `${sourceName} 不可用 · ${formatUnitSpan(sourceUnits, unitLabel)}` : null}
                {!sourceAvailable && !targetAvailable ? '；' : null}
                {!targetAvailable ? `${targetName} 不可用 · ${formatUnitSpan(targetUnits, unitLabel)}` : null}
              </p>
            )}
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700 text-2xl leading-none">
            ×
          </button>
        </div>

        <div className="space-y-4">
          {relations.length > 1 && (
            <div className="p-3 bg-[#f5f0e8] border border-[#d4a574] rounded-lg">
              <span className="text-sm text-[#8b4513]">共找到 <strong>{relations.length}</strong> 条关系记录</span>
            </div>
          )}

          {relations.map((relation, index) => (
            <div key={`${relation.source}-${relation.target}-${index}`} className="border border-[#d4c5b5] rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-sm font-semibold text-[#8b4513]">关系 {index + 1}:</span>
                <span className="text-sm text-gray-700">{relation.action}</span>
              </div>

              {relation.progressLabel && (
                <div className="mb-2 text-sm text-gray-600">进度：{relation.progressLabel}</div>
              )}

              {relation.timeText && <div className="mb-2 text-sm text-gray-600">原文时间：{relation.timeText}</div>}

              {relation.actionTypes.length > 0 && (
                <div className="mb-2">
                  <span className="font-semibold text-[#2c1810] text-sm">行动类型：</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {relation.actionTypes.map((type) => (
                      <span key={type} className="px-2 py-0.5 bg-[#f5f0e8] border border-[#d4a574] text-[#8b4513] rounded text-xs">
                        {type}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {relation.contexts.length > 0 && (
                <div>
                  <span className="font-semibold text-[#2c1810] text-sm">互动记录：</span>
                  <div className="mt-1 space-y-1 max-h-40 overflow-y-auto">
                    {relation.contexts.map((context, contextIndex) => (
                      <div key={contextIndex} className="p-2 bg-[#faf8f5] border border-[#d4c5b5] rounded text-xs text-gray-700">
                        {context}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}

          <div className="pt-3 border-t border-[#d4c5b5] grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="font-semibold text-[#2c1810]">总互动次数：</span>
              <span className="text-gray-700 ml-2">{totalWeight} 次</span>
            </div>
            {earliestProgress !== undefined && (
              <div>
                <span className="font-semibold text-[#2c1810]">最早进度：</span>
                <span className="text-gray-700 ml-2">{earliestProgress}</span>
              </div>
            )}
          </div>

          {relatedEvents && relatedEvents.length > 0 && (
            <div>
              <span className="font-semibold text-[#2c1810] text-sm">相关事件：</span>
              <div className="mt-2 space-y-2 max-h-48 overflow-y-auto">
                {relatedEvents.slice(0, 8).map((event) => (
                  <button
                    key={event.id}
                    onClick={() => handleEventClick(event)}
                    className="w-full text-left p-2 bg-[#faf8f5] border border-[#d4c5b5] rounded hover:bg-[#8b4513] hover:text-white hover:border-[#8b4513] transition-colors"
                  >
                    <div className="font-medium text-sm">{event.name}</div>
                    <div className="text-xs opacity-70">{event.progressLabel ?? `进度 ${event.progressStart ?? '未知'}`}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {allSourceUnits.length > 0 && (
            <div>
              <span className="font-semibold text-[#2c1810] text-sm">出现{unitLabel}：</span>
              <div className="flex flex-wrap gap-1 mt-1">
                {allSourceUnits.map((unit) => (
                  <span key={unit} className="px-2 py-0.5 bg-[#faf8f5] border border-[#d4c5b5] rounded text-xs">
                    {unitLabel}{unit}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface NetworkRoleRelationGroup {
  counterpartId: string;
  counterpartName: string;
  relations: RoleLinkUnified[];
  totalWeight: number;
  actionTypes: string[];
  sourceUnits: number[];
  earliestProgress: number | null;
}

interface NetworkRoleRelationsDetailProps {
  role: RoleNodeUnified | null;
  relationGroups: NetworkRoleRelationGroup[];
  onClose: () => void;
  onRelationClick?: (sourceId: string, targetId: string) => void;
  onEntityClick?: (entityName: string) => void;
  kb: UnifiedKnowledgeBase | null;
}

export function NetworkRoleRelationsDetail({
  role,
  relationGroups,
  onClose,
  onRelationClick,
  onEntityClick,
  kb,
}: NetworkRoleRelationsDetailProps) {
  if (!role) return null;

  const unitLabel = kb?.unit_label ?? '章节';

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 p-6 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-bold text-[#8b4513]">{role.name}的人物关系</h2>
            <p className="text-sm text-gray-500 mt-1">
              当前范围内共 {relationGroups.length} 个关系对象，优先列出和他直接形成关系边的人物。
            </p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700 text-2xl leading-none">
            ×
          </button>
        </div>

        <div className="space-y-3">
          {relationGroups.length > 0 ? (
            relationGroups.map((group) => (
              <div key={`${role.id}-${group.counterpartId}`} className="rounded-xl border border-[#d4c5b5] bg-[#faf8f5] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <button
                      onClick={() => onRelationClick?.(role.id, group.counterpartId)}
                      className="text-left text-lg font-semibold text-[#5d2e0c] hover:underline"
                    >
                      {role.name} × {group.counterpartName}
                    </button>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      <span className="px-2 py-1 rounded-full bg-[#8b4513] text-white">
                        关系记录 {group.relations.length}
                      </span>
                      <span className="px-2 py-1 rounded-full bg-[#d4a574] text-white">
                        互动权重 {group.totalWeight}
                      </span>
                      {group.earliestProgress !== null && (
                        <span className="px-2 py-1 rounded-full bg-[#f4ede4] text-[#8b4513]">
                          最早进度 {group.earliestProgress}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <button
                      onClick={() => onRelationClick?.(role.id, group.counterpartId)}
                      className="px-3 py-2 rounded-lg bg-[#8b4513] text-white text-sm hover:bg-[#6e360f] transition-colors"
                    >
                      查看关系详情
                    </button>
                    <button
                      onClick={() => {
                        onClose();
                        onEntityClick?.(group.counterpartName);
                      }}
                      className="text-xs text-[#8b4513] hover:underline"
                    >
                      在图中聚焦 {group.counterpartName}
                    </button>
                  </div>
                </div>

                {group.actionTypes.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {group.actionTypes.map((type) => (
                      <span
                        key={`${group.counterpartId}-${type}`}
                        className="px-2 py-1 rounded-full border border-[#d4a574] bg-white text-xs text-[#8b4513]"
                      >
                        {type}
                      </span>
                    ))}
                  </div>
                )}

                {group.sourceUnits.length > 0 && (
                  <div className="mt-3 text-sm text-gray-600">
                    出现{unitLabel}：{formatUnitSpan(group.sourceUnits, unitLabel)}
                  </div>
                )}
              </div>
            ))
          ) : (
            <div className="rounded-xl border border-[#d4c5b5] bg-[#faf8f5] p-4 text-sm text-gray-500">
              当前范围内，这个人物还没有形成可展示的关系边。
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
