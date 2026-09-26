import 'package:flutter/material.dart';

import '../domain/models/capability.dart';
import '../presentation/admin_page.dart';
import '../presentation/agent_history_page.dart';
import '../presentation/agent_home_view.dart';
import '../presentation/chat_page.dart';
import '../presentation/dynamic_provider_page.dart';
import '../presentation/file_center_page.dart';
import '../presentation/github_settings_page.dart';
import '../presentation/image_generation_page.dart';
import '../presentation/mcp_admin_page.dart';
import '../presentation/model_list_page.dart';
import '../presentation/ppt_page.dart';
import '../presentation/provider_settings_page.dart';
import '../presentation/task_queue_page.dart';
import '../presentation/virtual_girl_page.dart';
import '../presentation/workflow_page.dart';

/// Single source of truth for the workbench module entries.
final List<Capability> capabilityRegistry = <Capability>[
  Capability(
    id: 'agent',
    label: 'Agent 工作台',
    icon: Icons.rocket_launch_outlined,
    group: CapabilityGroup.workspace,
    builder: () => const AgentHomeView(),
  ),
  Capability(
    id: 'chat',
    label: '聊天',
    icon: Icons.chat_bubble_outline,
    group: CapabilityGroup.workspace,
    builder: () => const ChatPage(),
  ),
  Capability(
    id: 'agent_history',
    label: '会话历史',
    icon: Icons.history,
    group: CapabilityGroup.workspace,
    builder: () => const AgentHistoryPage(),
  ),
  Capability(
    id: 'ppt',
    label: 'PPT',
    icon: Icons.slideshow_outlined,
    group: CapabilityGroup.creation,
    builder: () => const PptPage(),
  ),
  Capability(
    id: 'image',
    label: '图片生成',
    icon: Icons.image_outlined,
    group: CapabilityGroup.creation,
    builder: () => const ImageGenerationPage(),
  ),
  Capability(
    id: 'workflow',
    label: '工作流执行',
    icon: Icons.account_tree_outlined,
    group: CapabilityGroup.creation,
    builder: () => const WorkflowPage(),
  ),
  Capability(
    id: 'girl',
    label: 'GirlAI 伴侣',
    icon: Icons.favorite_outline,
    group: CapabilityGroup.creation,
    builder: () => const VirtualGirlPage(),
  ),
  Capability(
    id: 'files',
    label: '文件中心',
    icon: Icons.folder_outlined,
    group: CapabilityGroup.data,
    builder: () => const FileCenterPage(),
  ),
  Capability(
    id: 'tasks',
    label: '任务队列',
    icon: Icons.list_alt_outlined,
    group: CapabilityGroup.data,
    builder: () => const TaskQueuePage(),
  ),
  Capability(
    id: 'provider',
    label: 'Provider 授权',
    icon: Icons.vpn_key_outlined,
    group: CapabilityGroup.system,
    builder: () => const ProviderSettingsPage(),
  ),
  Capability(
    id: 'models',
    label: '模型列表',
    icon: Icons.tune_outlined,
    group: CapabilityGroup.system,
    builder: () => const ModelListPage(),
  ),
  Capability(
    id: 'dynamic_provider',
    label: '动态 Provider',
    icon: Icons.cloud_sync_outlined,
    group: CapabilityGroup.system,
    builder: () => const DynamicProviderPage(),
  ),
  Capability(
    id: 'github',
    label: 'GitHub 设置',
    icon: Icons.code_outlined,
    group: CapabilityGroup.system,
    builder: () => const GithubSettingsPage(),
  ),
  Capability(
    id: 'admin',
    label: '管理员后台',
    icon: Icons.admin_panel_settings_outlined,
    group: CapabilityGroup.system,
    access: CapabilityAccess.admin,
    builder: () => const AdminPage(),
  ),
  Capability(
    id: 'mcp',
    label: 'MCP 管理',
    icon: Icons.hub_outlined,
    group: CapabilityGroup.system,
    access: CapabilityAccess.superadmin,
    builder: () => const McpAdminPage(),
  ),
];

/// Keeps the registry order while hiding modules above the session's level.
List<Capability> visibleCapabilities(String? permissionLevel) {
  return capabilityRegistry
      .where((capability) => _allows(capability.access, permissionLevel))
      .toList(growable: false);
}

bool _allows(CapabilityAccess access, String? permissionLevel) {
  return switch (access) {
    CapabilityAccess.normal => true,
    CapabilityAccess.admin =>
      permissionLevel == 'admin' || permissionLevel == 'superadmin',
    CapabilityAccess.superadmin => permissionLevel == 'superadmin',
  };
}
