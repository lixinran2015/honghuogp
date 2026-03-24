<template>
    <div style="display: flex; gap: 20px; flex-direction: column">
        <span class="header2">内容细览 </span>
        <div style="display: flex; gap: 20px; align-items: center">
            <update-time :time="lastCollectTime"></update-time>
            <el-button
                v-has-button="'dataAnalysisContent:updateData'"
                v-show="collcetDateEnabled"
                link
                @click="collectRefresh"
                :disabled="isCollecting || refreshFreezen"
                ><el-icon><Refresh /></el-icon>{{ isCollecting ? '正在更新' : '更新数据' }}
                <el-tooltip
                    class="box-item"
                    effect="dark"
                    placement="right"
                >
                    <template #content>
                        <div
                            v-html="
                                `1. 每日6:00更新前一日的数据<br />
                                2. 刷新数据后，${this.equityUsage.totalAmount || 30}分钟内不可再刷新数据<br />
                                3. 失效账号、禁用账号的数据可能不被统计<br />`
                            "
                        ></div>
                    </template>
                    <el-icon
                        style="margin-left: 10px"
                        size="14"
                        class="question-icon"
                        ><QuestionFilled
                    /></el-icon>
                </el-tooltip>
            </el-button>
        </div>
    </div>

    <!-- 子页面切换区域 -->
    <div class="tab-wrapper" style="margin-top: 20px">
        <el-tabs v-model="activeTab" @tab-change="handleTabChange">
            <!-- 使用 v-for 动态渲染有权限的标签页 -->
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
import { ref, computed, onMounted, getCurrentInstance, readonly, watch } from 'vue';
import updateTime from './components/update-time.vue';
import accountApi from '@/api/account/account-api';
import { useStatConfig } from '@/store/useStatConfig';
import { useUserInfo } from '@/store/useUserInfo';
import { useRouter } from 'vue-router'

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
const activeTab = ref(null); // 默认显示监测数据
const isCollecting = ref(false);
const refreshFreezen = ref(true);
const lastCollectTime = ref(undefined);
const equityUsage = ref({});
const availableTabs = ref([]); // 有权限访问的标签页

// 获取实例
const { proxy } = getCurrentInstance();
const router = useRouter()
const userInfo = useUserInfo().userInfo;

// 计算属性
const collcetDateEnabled = computed(() => {
    return equityUsage.value;
});

watch(() => proxy.$router.currentRoute.value.path, (newPath) => {
    if (newPath === '/data-analysis/content') {
        if (availableTabs.value.length > 0) {
             activeTab.value = availableTabs.value[0].path;
        }
    }
})

// 初始化权限控制的标签页
const initAvailableTabs = () => {
    availableTabs.value = [];
    allTabs.forEach(tab => {
        // 检查用户是否有访问该标签页的权限
        if (proxy.$permission.hasMenu(tab.path)) {
            availableTabs.value.push(tab);
        }
    });
    const currentPath = proxy.$router.currentRoute.value.path;
    if(availableTabs.value.find(tab => tab.path === currentPath)) {
        activeTab.value = currentPath;
    }
    // 如果当前激活的标签页没有权限，则切换到第一个有权限的标签页
    if (availableTabs.value.length > 0 && activeTab.value === null) {
        const redirectPath = availableTabs.value[0].path;
        activeTab.value = redirectPath;
        router.push(redirectPath);
    }
};

// 处理标签切换
const handleTabChange = (path) => {
    console.log('切换到:', path);
    activeTab.value = path;
    router.push(path);
};

// 刷新数据（公共方法）
const collectRefresh = () => {
    const refreshTime = new Date();
    const lastCollectTimeValue = lastCollectTime.value;
    localStorage.setItem(`collectRefresh${userInfo.userId}`, refreshTime);
    isCollecting.value = true;
    const holder = {
        success: resp => {
            lastCollectTime.value = refreshTime;
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
            lastCollectTime.value =
                resp.result.lastCollectTime != null
                    ? resp.result.lastCollectTime
                    : new Date(localStorage.getItem(`collectRefresh${userInfo.userId}`));
            refreshFreezen.value = lastCollectTime.value
                ? proxy.$dayjs(lastCollectTime.value)
                      .add(equityUsage.value.totalAmount, 'minute')
                      .isAfter(new Date())
                : false;
        },
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
</style>
