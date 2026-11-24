#define UNICODE
#define _UNICODE
#include <windows.h>
#include <dbghelp.h>
#include <cstdio>
#include <cwchar>
#include <string>
#include <vector>
#pragma comment(lib, "Dbghelp.lib")

static void print_hex(FILE* f, HANDLE process, const char* label, DWORD address, SIZE_T wanted) {
    std::vector<unsigned char> data(wanted);
    SIZE_T got = 0;
    BOOL ok = address != 0 && ReadProcessMemory(process, reinterpret_cast<LPCVOID>(static_cast<ULONG_PTR>(address)), data.data(), wanted, &got);
    std::fprintf(f, "%s_address=0x%08lX read_ok=%d bytes=%zu\n", label, address, ok ? 1 : 0, static_cast<size_t>(got));
    if (!ok) return;
    for (SIZE_T i = 0; i < got; i += 16) {
        std::fprintf(f, "%08lX: ", address + static_cast<DWORD>(i));
        for (SIZE_T j = 0; j < 16; ++j) {
            if (i + j < got) std::fprintf(f, "%02X ", data[i + j]); else std::fprintf(f, "   ");
        }
        std::fprintf(f, " | ");
        for (SIZE_T j = 0; j < 16 && i + j < got; ++j) {
            unsigned char c = data[i + j];
            std::fputc(c >= 0x20 && c <= 0x7E ? c : '.', f);
        }
        std::fputc('\n', f);
    }
}

int wmain(int argc, wchar_t** argv) {
    if (argc == 2 && std::wcscmp(argv[1], L"--help") == 0) {
        std::fwprintf(stdout, L"usage: debug_capture.exe <exe> <working_dir> <dump.dmp> <capture.txt>\n");
        return 0;
    }
    if (argc != 5) {
        std::fwprintf(stderr, L"expected 4 arguments; use --help\n");
        return 2;
    }
    const wchar_t* exe = argv[1];
    const wchar_t* cwd = argv[2];
    const wchar_t* dump_path = argv[3];
    const wchar_t* capture_path = argv[4];
    DWORD attrs = GetFileAttributesW(exe);
    if (attrs == INVALID_FILE_ATTRIBUTES || (attrs & FILE_ATTRIBUTE_DIRECTORY)) {
        std::fwprintf(stderr, L"executable not found: %ls\n", exe);
        return 3;
    }
    attrs = GetFileAttributesW(cwd);
    if (attrs == INVALID_FILE_ATTRIBUTES || !(attrs & FILE_ATTRIBUTE_DIRECTORY)) {
        std::fwprintf(stderr, L"working directory not found: %ls\n", cwd);
        return 4;
    }
    FILE* log = nullptr;
    if (_wfopen_s(&log, capture_path, L"wb") != 0 || !log) {
        std::fwprintf(stderr, L"cannot create capture log: %ls\n", capture_path);
        return 5;
    }
    std::wstring cmd = L"\"" + std::wstring(exe) + L"\"";
    std::vector<wchar_t> mutable_cmd(cmd.begin(), cmd.end());
    mutable_cmd.push_back(L'\0');
    STARTUPINFOW si{}; si.cb = sizeof(si);
    PROCESS_INFORMATION pi{};
    if (!CreateProcessW(exe, mutable_cmd.data(), nullptr, nullptr, FALSE, DEBUG_ONLY_THIS_PROCESS, nullptr, cwd, &si, &pi)) {
        std::fprintf(log, "CreateProcessW failed error=%lu\n", GetLastError());
        std::fclose(log);
        return 6;
    }
    std::fprintf(log, "pid=%lu\n", pi.dwProcessId);
    std::fflush(log);
    DWORD image_base = 0;
    bool captured = false;
    bool running = true;
    DWORD exit_code = STILL_ACTIVE;
    while (running) {
        DEBUG_EVENT ev{};
        if (!WaitForDebugEvent(&ev, INFINITE)) {
            std::fprintf(log, "WaitForDebugEvent failed error=%lu\n", GetLastError());
            break;
        }
        DWORD cont = DBG_CONTINUE;
        switch (ev.dwDebugEventCode) {
        case CREATE_PROCESS_DEBUG_EVENT:
            image_base = static_cast<DWORD>(reinterpret_cast<ULONG_PTR>(ev.u.CreateProcessInfo.lpBaseOfImage));
            std::fprintf(log, "image_base=0x%08lX\n", image_base);
            if (ev.u.CreateProcessInfo.hFile) CloseHandle(ev.u.CreateProcessInfo.hFile);
            break;
        case LOAD_DLL_DEBUG_EVENT:
            if (ev.u.LoadDll.hFile) CloseHandle(ev.u.LoadDll.hFile);
            break;
        case EXCEPTION_DEBUG_EVENT: {
            const auto& ex = ev.u.Exception.ExceptionRecord;
            DWORD addr = static_cast<DWORD>(reinterpret_cast<ULONG_PTR>(ex.ExceptionAddress));
            std::fprintf(log, "exception code=0x%08lX address=0x%08lX first_chance=%lu thread=%lu\n", ex.ExceptionCode, addr, ev.u.Exception.dwFirstChance, ev.dwThreadId);
            bool target = ex.ExceptionCode == EXCEPTION_ACCESS_VIOLATION && (image_base == 0 || addr == image_base + 0x000D11E8);
            if (target && !captured) {
                HANDLE thread = OpenThread(THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, ev.dwThreadId);
                CONTEXT ctx{}; ctx.ContextFlags = CONTEXT_ALL;
                BOOL ctx_ok = thread && GetThreadContext(thread, &ctx);
                std::fprintf(log, "context_ok=%d\n", ctx_ok ? 1 : 0);
                if (ctx_ok) {
                    std::fprintf(log, "EAX=%08lX EBX=%08lX ECX=%08lX EDX=%08lX ESI=%08lX EDI=%08lX EBP=%08lX ESP=%08lX EIP=%08lX EFLAGS=%08lX\n", ctx.Eax,ctx.Ebx,ctx.Ecx,ctx.Edx,ctx.Esi,ctx.Edi,ctx.Ebp,ctx.Esp,ctx.Eip,ctx.EFlags);
                    print_hex(log, pi.hProcess, "eip", ctx.Eip >= 64 ? ctx.Eip - 64 : ctx.Eip, 256);
                    print_hex(log, pi.hProcess, "stack", ctx.Esp, 4096);
                    print_hex(log, pi.hProcess, "eax", ctx.Eax, 512);
                    print_hex(log, pi.hProcess, "ebx", ctx.Ebx, 256);
                    print_hex(log, pi.hProcess, "ecx", ctx.Ecx, 256);
                    print_hex(log, pi.hProcess, "edx", ctx.Edx, 256);
                    print_hex(log, pi.hProcess, "esi", ctx.Esi, 256);
                    print_hex(log, pi.hProcess, "edi", ctx.Edi, 256);
                    print_hex(log, pi.hProcess, "ebp", ctx.Ebp, 256);
                }
                HANDLE dump = CreateFileW(dump_path, GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
                BOOL dump_ok = FALSE;
                if (dump != INVALID_HANDLE_VALUE) {
                    MINIDUMP_EXCEPTION_INFORMATION mei{};
                    EXCEPTION_POINTERS pointers{};
                    pointers.ExceptionRecord = const_cast<PEXCEPTION_RECORD>(&ex);
                    pointers.ContextRecord = ctx_ok ? &ctx : nullptr;
                    mei.ThreadId = ev.dwThreadId;
                    mei.ExceptionPointers = ctx_ok ? &pointers : nullptr;
                    mei.ClientPointers = FALSE;
                    MINIDUMP_TYPE type = static_cast<MINIDUMP_TYPE>(MiniDumpWithFullMemory | MiniDumpWithHandleData | MiniDumpWithUnloadedModules | MiniDumpWithFullMemoryInfo | MiniDumpWithThreadInfo | MiniDumpWithProcessThreadData);
                    dump_ok = MiniDumpWriteDump(pi.hProcess, pi.dwProcessId, dump, type, ctx_ok ? &mei : nullptr, nullptr, nullptr);
                    std::fprintf(log, "minidump_ok=%d error=%lu\n", dump_ok ? 1 : 0, dump_ok ? 0 : GetLastError());
                    CloseHandle(dump);
                } else {
                    std::fprintf(log, "CreateFileW dump failed error=%lu\n", GetLastError());
                }
                if (thread) CloseHandle(thread);
                captured = true;
                std::fflush(log);
            }
            cont = DBG_EXCEPTION_NOT_HANDLED;
            break;
        }
        case EXIT_PROCESS_DEBUG_EVENT:
            exit_code = ev.u.ExitProcess.dwExitCode;
            std::fprintf(log, "exit_code=0x%08lX\n", exit_code);
            running = false;
            break;
        default:
            break;
        }
        ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont);
    }
    std::fprintf(log, "captured=%d final_exit=0x%08lX\n", captured ? 1 : 0, exit_code);
    std::fclose(log);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return captured ? 0 : 7;
}
