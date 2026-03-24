<template>
    <div style="display: flex; gap: 20px; flex-direction: column">
        <span class="header2">内容细览 </span>
        <div style="display: flex; gap: 20px; align-items: center">
            <update-time :time="lastCollectTime"></update-time>
            <el-button
                v-has-button="'dataAnalysisContent:updateData'"
                v-show="collectDateEnabled"
                link
                @click="collectRefresh"
                :disabled="isCollecting || refreshFreezen"
            >
                <el-icon><Refresh /></el-icon>{{ isCollecting ? '正在更新' : '更新数据' }}
                <el-tooltip
                    class="box-item"
                    effect="dark"
                    placement="right"
                >
                    <template #content>
                        <div
                            v-html="
                                `1. 每日6:00更新前一日的数据<br />
                                2. 刷新数据后，${equityUsage.totalAmount || 30}分钟内不可再刷新数据<br />
                                3. 失效账号、禁用账号的数据可能不被统计<br />`
                            "
                        ></div>
                    </template>
                    <el-icon
                        style="margin-left: 10px"
                        size="14"
                        class="question-icon"
                    >
                        <QuestionFilled />
                    </el-icon>
                </el-tooltip>
            </el-button>
        </div>
    </div>

    <!-- 子页面切换区域：增加无权限提示，避免空白 -->
    <div class="tab-wrapper" style="margin-top: 20px">
        <!-- 无权限时显示提示，而非空白 -->
        <div v-if="availableTabs.length === 0" class="no-permission">
            暂无访问权限，请联系管理员
        </div>
        <el-tabs v-else v-model="activeTab" @tab-change="handleTabChange">
            <el-tab-pane 
                v-for="tab in availableTabs" 
                :key="tab.path"
                :label="tab.label" 
                :name="tab.path"
            >
                 <router-view :key="tab.path" />
            </el-tab-pane>
        </el-tabs>
    </div>
</template>

<script setup>
import { ref, computed, onMounted, getCurrentInstance, readonly, watch, nextTick } from 'vue';
import updateTime from './components/update-time.vue';
import accountApi from '@/api/account/account-api';
import { useStatConfig } from '@/store/useStatConfig';
import { useUserInfo } from '@/store/useUserInfo';
import { useRouter, useRoute } from 'vue-router'

// 定义所有可能的标签页配置
const allTabs = readonly([
    {
        name: 'monitor',
        label: '内容监测数据',
        path: '/data-analysis/content/monitor'
    },
    {
        name: 'dispatch',
        label: '内容分发数据',
        path: '/data-analysis/content/dispatch'
    }
]);

// 响应式数据
const activeTab = ref(''); // 修复1：初始值改为空字符串，避免null导致的渲染问题
const isCollecting = ref(false);
const refreshFreezen = ref(true);
const lastCollectTime = ref(undefined);
const equityUsage = ref({});
const availableTabs = ref([]); // 有权限访问的标签页

// 获取实例和路由（修复2：改用useRoute，更符合Vue3规范）
const { proxy } = getCurrentInstance();
const router = useRouter();
const route = useRoute(); // 新增：获取当前路由对象
const userInfo = useUserInfo().userInfo;

// 计算属性：与 content-old 一致，equityUsage 为对象时显示按钮（含空对象）
const collectDateEnabled = computed(() => {
    const eq = equityUsage.value;
    return eq && typeof eq === 'object';
});

// 修复4：优化路由监听逻辑，增加跳转和时机控制
watch(() => route.path, (newPath) => {
    if (newPath === '/data-analysis/content') {
        nextTick(() => { // 等待DOM和权限列表初始化完成
            if (availableTabs.value.length > 0) {
                const firstTabPath = availableTabs.value[0].path;
                activeTab.value = firstTabPath;
                // 关键：不仅设置activeTab，还要触发路由跳转，加载子页面
                router.push(firstTabPath).catch(err => {
                    console.warn('路由跳转失败:', err); // 增加错误捕获，避免控制台报错
                });
            }
        });
    }
}, { immediate: true }); // 新增：立即执行一次，确保初始化时生效

// 初始化权限控制的标签页（修复5：优化逻辑，适配路由监听）
const initAvailableTabs = () => {
    availableTabs.value = [];
    allTabs.forEach(tab => {
        // 检查用户是否有访问该标签页的权限
        if (proxy?.$permission?.hasMenu(tab.path)) {
            availableTabs.value.push(tab);
        }
    });

    const currentPath = route.path;
    // 优先匹配当前路由的标签页
    const matchedTab = availableTabs.value.find(tab => tab.path === currentPath);
    
    if (matchedTab) {
        activeTab.value = currentPath;
    } else if (availableTabs.value.length > 0 && currentPath === '/data-analysis/content') {
        // 父路径且有权限，跳转到第一个子标签页
        const firstTabPath = availableTabs.value[0].path;
        activeTab.value = firstTabPath;
        router.push(firstTabPath).catch(err => console.warn(err));
    } else if (availableTabs.value.length > 0 && activeTab.value === '') {
        // 无匹配路由，但有权限，跳转到第一个标签页
        const redirectPath = availableTabs.value[0].path;
        activeTab.value = redirectPath;
        router.push(redirectPath).catch(err => console.warn(err));
    }
};

// 处理标签切换（修复6：增加错误捕获）
const handleTabChange = (path) => {
    console.log('切换到:', path);
    activeTab.value = path;
    router.push(path).catch(err => {
        console.warn('标签切换路由失败:', err);
    });
};

// 刷新数据（公共方法：修复7：成功后重置isCollecting状态）
const collectRefresh = () => {
    const refreshTime = new Date();
    const lastCollectTimeValue = lastCollectTime.value;
    localStorage.setItem(`collectRefresh${userInfo.userId}`, refreshTime);
    isCollecting.value = true;
    const holder = {
        success: resp => {
            lastCollectTime.value = refreshTime;
            isCollecting.value = false; // 新增：成功后重置状态，避免按钮一直显示“正在更新”
        },
        error: () => {
            localStorage.removeItem(`collectRefresh${userInfo.userId}`);
            isCollecting.value = false;
            lastCollectTime.value = lastCollectTimeValue;
        },
    };
    accountApi.collectAll(holder);
};

// 获取采集状态（公共方法）
const collectStatus = () => {
    const holder = {
        success: resp => {
            isCollecting.value = resp.result.isCollecting;
            const stored = localStorage.getItem(`collectRefresh${userInfo.userId}`);
            lastCollectTime.value =
                resp.result.lastCollectTime != null
                    ? resp.result.lastCollectTime
                    : (stored ? new Date(stored) : undefined);
            const dayjsFn = proxy?.$dayjs;
            refreshFreezen.value = lastCollectTime.value && dayjsFn
                ? dayjsFn(lastCollectTime.value)
                      .add(equityUsage.value.totalAmount || 30, 'minute')
                      .isAfter(new Date())
                : false;
        },
        error: () => { // 新增：错误回调，避免接口失败导致状态异常
            console.error('获取采集状态失败');
        }
    };
    accountApi.getCollectStatus(holder);
};

// 组件挂载时初始化
onMounted(() => {
    equityUsage.value = useStatConfig().getStatRefreshEquity();
    collectStatus();
    initAvailableTabs(); // 初始化权限控制的标签页
});
</script>

<style scoped>
.tab-wrapper {
    background: #fff;
    border-radius: 8px;
    padding: 20px;
}

/* 自定义标签样式 */
:deep(.el-tabs__header) {
    margin-bottom: 20px;
}

:deep(.el-tabs__item) {
    font-size: 16px;
    font-weight: 500;
}

:deep(.el-tabs__item.is-active) {
    color: #409eff;
}

/* 新增：无权限提示样式，避免空白 */
.no-permission {
    text-align: center;
    padding: 40px 0;
    color: #999;
    font-size: 14px;
}

.question-icon {
    cursor: pointer;
}
</style>