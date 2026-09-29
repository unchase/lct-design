import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',timeout:180000,workers:1,use:{baseURL:process.env.LCT_TEST_URL||'http://127.0.0.1:8012',viewport:{width:1440,height:1000},headless:true},reporter:'list'});
